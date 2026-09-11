#!/usr/bin/env python3
"""Full screen is declared per window family, not taken away from every window at once.

AppController used to replace a private AppKit method, -[NSWindow
showsFullScreenButton], with one returning NO, for every window in the process.
Measured on macOS 26.6.2, that method is still live and still decides the button:
with the replacement installed, a window declaring FullScreenPrimary exposes no
accessibility full-screen button either - so the Database window, which asks for
full screen, could not offer it. And a private method can be renamed away without
notice, taking the intent with it.

The intent belongs to each family, in public API:

  Database, Query/Retrieve  FullScreenPrimary   they host a full-screen Space
  2D viewer, 3D windows     FullScreenAuxiliary they have their own full screen,
                                                fullScreenMenu:, which moves the
                                                content view into a borderless
                                                window; both cannot own it

The 3D declaration hangs on setWindow: rather than windowDidLoad: two subclasses
override windowDidLoad without calling super, so a declaration there would miss
them. That is the property checked below - no subclass may override setWindow:.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []


def read(name):
    return (root / 'Horos/Sources' / name).read_bytes().decode('latin1')


application = read('AppController.m')
viewer = read('ViewerController.m')
window3d = read('Window3DController.m')

# --- nothing replaces a private AppKit method for this any more ---------------
for gone in ('jr_swizzleMethod', 'HOROS_showsFullScreenButton', 'showsFullScreenButton',
             'NSWindow (FFS)', 'JRSwizzle'):
    if gone in application:
        failures.append('AppController.m still mentions %s' % gone)
# The swizzling helper existed only for that, so it goes with it - and stays gone,
# rather than waiting in the project for the next private method.
for orphan in ('JRSwizzle.h', 'JRSwizzle.m'):
    if (root / 'Horos/Sources' / orphan).exists():
        failures.append('%s is still in the tree with nothing using it' % orphan)
    if orphan in (root / 'Horos.xcodeproj/project.pbxproj').read_text():
        failures.append('%s is still listed in the Xcode project' % orphan)

# --- the two families that decline say so through the helper ------------------
if '[HorosFullScreenWindowSupport declineNativeFullScreen: self.window];' not in viewer:
    failures.append('the 2D viewer no longer declares that it declines native full screen')
if 'NSWindowCollectionBehaviorFullScreen' in viewer:
    failures.append('the 2D viewer still composes the collection behaviour inline')

# The viewer's accessory panels are part of the same family: they follow the
# viewer's window and have no Space of their own.
for name, marker in (('LoupeController.m', 'initWithWindowNibName:@"Loupe"'),
                     ('ThickSlabController.mm', 'initWithWindowNibName:@"ThickSlab"')):
    text = read(name)
    if marker not in text:
        failures.append('%s no longer loads its nib where the declaration was made' % name)
    elif 'declineNativeFullScreen' not in text:
        failures.append('%s does not decline native full screen' % name)

at = window3d.find('- (void) setWindow: (NSWindow*) window')
body = window3d[at:at + 300] if at >= 0 else ''
if not body:
    failures.append('Window3DController does not declare its full-screen behaviour at setWindow:')
else:
    if '[super setWindow: window]' not in body:
        failures.append('Window3DController overrides setWindow: without calling super')
    if 'declineNativeFullScreen' not in body:
        failures.append('Window3DController does not decline native full screen')

# Every 3D window inherits that override, so none of them may hide it. This is
# the reason the declaration is not in windowDidLoad, which two of them override
# without calling super.
subclasses = []
for header in sorted((root / 'Horos/Sources').glob('*.h')):
    text = header.read_bytes().decode('latin1')
    if re.search(r'@interface\s+(\w+)\s*:\s*Window3DController\b', text):
        subclasses.append(re.search(r'@interface\s+(\w+)\s*:\s*Window3DController\b', text).group(1))
if len(subclasses) < 8:
    failures.append('only %d Window3DController subclasses found; the search is wrong' % len(subclasses))
for source in sorted(list((root / 'Horos/Sources').glob('*.m')) +
                     list((root / 'Horos/Sources').glob('*.mm'))):
    text = source.read_bytes().decode('latin1')
    owner = re.search(r'@implementation\s+(\w+)', text)
    if owner and owner.group(1) in subclasses and re.search(r'^-\s*\(void\)\s*setWindow:', text, re.M):
        failures.append('%s overrides setWindow:, so it would not inherit the declaration'
                        % source.name)

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

main = r'''import AppKit

// Declining keeps the flags that are about Spaces and cycling, and replaces only
// the full-screen ones.
let mixed: NSWindow.CollectionBehavior = [.managed, .participatesInCycle, .fullScreenPrimary]
let declined = FullScreenWindowSupport.auxiliaryBehavior(from: mixed)
precondition(declined.contains(.fullScreenAuxiliary))
precondition(!declined.contains(.fullScreenPrimary) && !declined.contains(.fullScreenNone))
precondition(declined.contains(.managed) && declined.contains(.participatesInCycle))
precondition(FullScreenWindowSupport.auxiliaryBehavior(from: declined) == declined)
precondition(!FullScreenWindowSupport.auxiliaryBehavior(from: [.fullScreenNone]).contains(.fullScreenNone))

// The two directions undo each other, so a window can be moved between families.
let primary = FullScreenWindowSupport.primaryBehavior(from: declined)
precondition(primary.contains(.fullScreenPrimary) && !primary.contains(.fullScreenAuxiliary))

let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 300),
                      styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: true)
FullScreenWindowSupport.enablePrimaryFullScreen(window)
precondition(window.collectionBehavior.contains(.fullScreenPrimary))
FullScreenWindowSupport.declineNativeFullScreen(window)
precondition(window.collectionBehavior.contains(.fullScreenAuxiliary))
precondition(!window.collectionBehavior.contains(.fullScreenPrimary))

// AppKit's own answer, which is the point of the declaration: Enter Full Screen
// is offered for primary and refused for auxiliary, so a window that declines is
// left on zoom. What a window that declares *nothing* gets is not asserted here:
// measured inside the launched application it is offered, and measured in this
// command-line tool it is not, which is why the swizzle's reach was established
// against the running application and not here.
let item = NSMenuItem(title: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)),
                      keyEquivalent: "")
func offersFullScreen(_ behavior: NSWindow.CollectionBehavior) -> Bool {
    let scratch = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 300),
                           styleMask: [.titled, .resizable, .closable, .miniaturizable],
                           backing: .buffered, defer: true)
    scratch.collectionBehavior = behavior
    return scratch.validateMenuItem(item)
}
precondition(offersFullScreen(.fullScreenPrimary))
precondition(!offersFullScreen(.fullScreenAuxiliary))
precondition(!offersFullScreen(.fullScreenNone))

// And nothing here is holding a private selector.
precondition(!FullScreenWindowSupport.responds(to: Selector(("showsFullScreenButton"))))

// A controller may be asked before its nib has a window.
FullScreenWindowSupport.declineNativeFullScreen(nil)

print("PASS: declining is auxiliary, it is reversible, and AppKit refuses full screen for it")
'''

with tempfile.TemporaryDirectory(prefix='horos-full-screen-policy-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    build = subprocess.run(['swiftc', str(root / 'Horos/Sources/FullScreenWindowSupport.swift'),
                            str(p / 'main.swift'), '-o', str(p / 'test')],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2000:])
        sys.exit('the full-screen helper did not compile')
    checks = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    print((checks.stdout + checks.stderr).strip())
    if checks.returncode:
        failures.append('the helper does not declare what the families need')

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: each family declares its own full-screen behaviour, in public API')
