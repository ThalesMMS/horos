#!/usr/bin/env python3
"""Verify production full-screen behavior, resize limits and the Query/Retrieve command."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
query=(root/'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')
for statement in ['[HorosFullScreenWindowSupport enablePrimaryFullScreen: [self window]];',
                  'designedMinimumSize = [[self window] minSize];',
                  '[HorosWindowSizeLimits applyMinimumSize: designedMinimumSize toWindow: [self window]];',
                  'NSApplicationDidChangeScreenParametersNotification',
                  '- (IBAction) fullScreenMenu:(id) sender',
                  '[HorosFullScreenWindowSupport toggleFullScreen: [self window]];',
                  '- (void) windowDidExitFullScreen:(NSNotification *)notification']:
    assert statement in query, f'missing in QueryController.mm: {statement}'
assert 'setLevel: NSFloatingWindowLevel' not in query, 'the Query window still sets the floating level directly'
browser=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
assert '[HorosFullScreenWindowSupport enablePrimaryFullScreen: self.window];' in browser
assert 'NSWindowCollectionBehaviorFullScreenPrimary' not in browser, 'the database still builds the behavior inline'
source=r'''
import AppKit
// Unrelated flags survive; auxiliary and none give way to primary.
let managed: NSWindow.CollectionBehavior = [.managed, .participatesInCycle, .fullScreenAuxiliary]
let primary = FullScreenWindowSupport.primaryBehavior(from: managed)
precondition(primary.contains(.fullScreenPrimary))
precondition(!primary.contains(.fullScreenAuxiliary))
precondition(primary.contains(.managed) && primary.contains(.participatesInCycle))
precondition(!FullScreenWindowSupport.primaryBehavior(from: [.fullScreenNone]).contains(.fullScreenNone))
precondition(FullScreenWindowSupport.primaryBehavior(from: primary) == primary)
// Keep on Top floats only while windowed.
precondition(FullScreenWindowSupport.level(keepOnTop: true, fullScreen: false) == .floating)
precondition(FullScreenWindowSupport.level(keepOnTop: true, fullScreen: true) == .normal)
precondition(FullScreenWindowSupport.level(keepOnTop: false, fullScreen: false) == .normal)
precondition(FullScreenWindowSupport.level(keepOnTop: false, fullScreen: true) == .normal)
let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 300),
                      styleMask: [.titled, .resizable, .closable], backing: .buffered, defer: true)
FullScreenWindowSupport.enablePrimaryFullScreen(window)
precondition(window.collectionBehavior.contains(.fullScreenPrimary))
FullScreenWindowSupport.applyLevel(window, keepOnTop: true)
precondition(window.level == .floating)
FullScreenWindowSupport.applyLevel(window, keepOnTop: false)
precondition(window.level == .normal)
// AppKit refuses the full-screen mask outside a real transition, so report it.
final class FullScreenProbe: NSWindow {
    override var styleMask: NSWindow.StyleMask {
        get { [.titled, .resizable, .fullScreen] }
        set { _ = newValue }
    }
}
let entered = FullScreenProbe(contentRect: NSRect(x: 0, y: 0, width: 400, height: 300),
                              styleMask: [.titled, .resizable], backing: .buffered, defer: true)
FullScreenWindowSupport.applyLevel(entered, keepOnTop: true)
precondition(entered.level == .normal, "a full-screen window must not float over the menu bar")
// A minimum bigger than the display is what displaced the window's origin.
let laptop = NSRect(x: 0, y: 25, width: 1366, height: 703)
let designed = NSSize(width: 914, height: 704)
precondition(WindowSizeLimits.minimum(designed, visibleFrame: laptop) == NSSize(width: 914, height: 703))
let wide = NSRect(x: 0, y: 79, width: 1680, height: 940)
precondition(WindowSizeLimits.minimum(designed, visibleFrame: wide) == designed)
precondition(WindowSizeLimits.minimum(designed, visibleFrame: NSRect(x: 0, y: 0, width: 800, height: 600))
             == NSSize(width: 800, height: 600))
precondition(WindowSizeLimits.minimum(designed, visibleFrame: .zero) == designed)
precondition(WindowSizeLimits.minimum(.zero, visibleFrame: wide) == .zero)
precondition(WindowSizeLimits.minimum(NSSize(width: CGFloat.nan, height: 704), visibleFrame: wide)
             == NSSize(width: 0, height: 704))
let limited = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 914, height: 672),
                       styleMask: [.titled, .resizable], backing: .buffered, defer: true)
limited.minSize = designed
WindowSizeLimits.apply(designed, to: limited)
precondition(limited.minSize.width <= designed.width && limited.minSize.height <= designed.height)
precondition(limited.minSize.height <= (NSScreen.main?.visibleFrame.height ?? designed.height))
print("PASS: primary behavior preserves unrelated flags, minimum sizes bounded by the display, Keep on Top floats only while windowed, production command and delegate present")
'''
with tempfile.TemporaryDirectory(prefix='horos-query-fullscreen-') as tmp:
    p=Path(tmp);(p/'main.swift').write_text(source)
    subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/FullScreenWindowSupport.swift'),
                    str(root/'Horos/Sources/WindowSizeLimits.swift'),
                    str(root/'Horos/Sources/DatabaseWindowPlacement.swift'),
                    str(p/'main.swift'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
