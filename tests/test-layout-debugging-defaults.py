#!/usr/bin/env python3
"""The purple window is AppKit's, and Horos stops leaving it switched on.

A report of "a purple window appeared with only Horos open" (horosproject/horos#180)
is AppKit's constraint visualizer: the default
`NSConstraintBasedLayoutVisualizeMutuallyExclusiveConstraints` makes AppKit draw
a window of its own over the one it is complaining about. Horos used to turn that
on by *writing* the key into the person's preference file on every debug launch
and writing it off again on quit - so any run that ended another way left it on
for every later run, of any build. AppKit, asked why the window is there, then
lists every preference domain on the Mac that carries the key, which is how one
badly-scoped debugging aid reads as two applications interfering.

The visualizer still works for a debug build, from the registration domain, which
is consulted the same way and never written down; and the log says when it is on,
so the next such report answers itself.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/LayoutDebuggingDefaults.swift'
if not source.exists():
    print('FAIL: %s is gone' % source.name)
    sys.exit(1)

application = (root / 'Horos/Sources/AppController.m').read_bytes().decode('utf-8')
key = 'NSConstraintBasedLayoutVisualizeMutuallyExclusiveConstraints'

# --- nothing writes the key into the preference file any more -----------------
written = re.findall(r'setBool:\s*(?:YES|NO)\s*forKey:\s*@"%s"' % key, application)
if written:
    failures.append('AppController still writes %s into the preference domain, %d time(s)'
                    % (key, len(written)))

# --- and the debug build still gets the visualizer ---------------------------
adoption = re.search(r'#ifdef NDEBUG\s*\[HorosLayoutDebuggingDefaults adoptForThisProcessOnly:\s*NO\];'
                     r'\s*#else\s*\[HorosLayoutDebuggingDefaults adoptForThisProcessOnly:\s*YES\];'
                     r'\s*#endif', application)
if not adoption:
    failures.append('a debug build no longer switches the visualizer on for its own process, '
                    'or a release build no longer leaves it alone')

# --- the log carries the answer ----------------------------------------------
if 'reportForCurrentProcess' not in application:
    failures.append('the startup log never says when AppKit layout debugging is on')

for failure in failures:
    print('FAIL: %s' % failure)

main = r'''import Foundation

let key = LayoutDebuggingDefaults.visualizerKey
let logKey = LayoutDebuggingDefaults.logKey
assert(key == "NSConstraintBasedLayoutVisualizeMutuallyExclusiveConstraints", key)
assert(LayoutDebuggingDefaults.keys == [key, logKey])

// A preference written by hand is a string, an argument is "YES", code writes a
// boolean: the same switch, three spellings.
for on in [true as Any, NSNumber(value: 1), "YES", "1", "true"] {
    assert(LayoutDebuggingDefaults.isOn(on), "\(on) should read as on")
}
for off in [false as Any, NSNumber(value: 0), "NO", "0", ""] {
    assert(!LayoutDebuggingDefaults.isOn(off), "\(off) should read as off")
}
assert(!LayoutDebuggingDefaults.isOn(nil))
// Absent is not the same as off: only the second is worth a sentence.
assert(!LayoutDebuggingDefaults.isOff(nil))
assert(LayoutDebuggingDefaults.isOff("NO"))

// Nothing to say when nobody has touched either key.
assert(LayoutDebuggingDefaults.report(settings: [:], persistedIn: nil) == nil)
assert(LayoutDebuggingDefaults.report(settings: [key: false], persistedIn: "org.x") == nil)
assert(LayoutDebuggingDefaults.report(settings: [logKey: true], persistedIn: nil) == nil)

// On and written down: the sentence says whose window it is and how to be rid of it.
guard let purple = LayoutDebuggingDefaults.report(settings: [key: "YES"],
                                                  persistedIn: "org.horosproject.horos") else {
    fatalError("nothing was reported for a visualizer that is switched on")
}
assert(purple.contains("purple"), purple)
assert(purple.contains("AppKit"), purple)
assert(purple.contains("defaults delete org.horosproject.horos \(key)"), purple)
// The whole point: it is not Horos's window and not a plugin's.
assert(purple.contains("not to Horos") && purple.contains("plugin"), purple)
// And that AppKit's list of domains is not a list of applications reading it.
assert(purple.contains("preference domain"), purple)

// On because this run asked for it: there is nothing to delete, and saying there
// is would send somebody after a key that is not in the file.
guard let asked = LayoutDebuggingDefaults.report(settings: [key: true], persistedIn: nil) else {
    fatalError("nothing was reported for a visualizer switched on by this run")
}
assert(asked.contains("purple"), asked)
assert(!asked.contains("defaults delete"), asked)
assert(asked.contains("nothing was written"), asked)

// The other key only matters when somebody has turned it off.
guard let quiet = LayoutDebuggingDefaults.report(settings: [logKey: false], persistedIn: nil) else {
    fatalError("nothing was reported for constraint logging that is switched off")
}
assert(quiet.contains(logKey), quiet)
assert(!quiet.contains("purple"), quiet)

let both = LayoutDebuggingDefaults.report(settings: [key: true, logKey: "NO"], persistedIn: "org.x")!
assert(both.contains("purple") && both.contains(logKey), both)

print("PASS: the window is named as AppKit's, with the domain to delete it from")
'''

with tempfile.TemporaryDirectory(prefix='horos-layout-debugging-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    subprocess.run(['swiftc', str(source), str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

if failures:
    sys.exit(1)
print('ok: the purple window is AppKit\'s, said so in the log, and never left on in the preferences')
