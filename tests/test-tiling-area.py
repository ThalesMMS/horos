#!/usr/bin/env python3
"""Horos lays its windows out inside a chosen part of the screen, not all of it.

Tiling took the whole visible frame of every screen, which is the wrong answer on
a wide display where somebody wants a report application beside the images rather
than behind them. The area is now a rectangle in fractions of the visible frame,
kept per screen, and `+[AppController usefullRectForScreen:]` - the one place
that decides where Horos puts a window - returns it.

The arithmetic is a pure function, so the cases that matter can be stated: a
fraction that runs off the edge, a reservation so large that nothing usable is
left, and a screen nobody has configured.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
application = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')

at = application.find('+ (NSRect) usefullRectForScreen: (NSScreen*) screen showFloatingWindows:')
body = application[at:application.index('\n}', at)] if at >= 0 else ''
if not body:
    failures.append('usefullRectForScreen:showFloatingWindows: is gone')
else:
    if 'HorosTilingArea rectForScreen:' not in body:
        failures.append('the usable rectangle is still the whole visible frame')
    # The floating panels have to come out of the chosen area, not out of the
    # screen, so the narrowing is first.
    area = body.find('HorosTilingArea rectForScreen:')
    panel = body.find('exposedHeight')
    if area >= 0 and panel >= 0 and area > panel:
        failures.append('the panels are taken off the screen before the area is chosen')

# The menu is built in code because there is one nib per language.
for wanted in ('- (void) buildTilingAreaMenu', '@selector(setTilingArea:)',
               'HorosTilingArea presetNames', 'HorosTilingArea presetNameForScreen:'):
    if wanted not in application:
        failures.append('AppController no longer has %s' % wanted)

# Each viewer has its own toolbar panel and they place themselves from the screen
# parameters, so changing the area has to tell all of them, not just the front one.
at = application.find('- (IBAction) setTilingArea:')
action = application[at:at + 1400] if at >= 0 else ''
if 'NSApplicationDidChangeScreenParametersNotification' not in action:
    failures.append('changing the area leaves the other viewers\' panels where they were')

# And the panels themselves have to ask for the area rather than the whole screen.
for name in ('ThumbnailsListPanel.m', 'ToolbarPanel.m'):
    panel = (root / 'Horos/Sources' / name).read_bytes().decode('latin1')
    if 'HorosTilingArea rectForScreen:' not in panel:
        failures.append('%s still places itself on the whole visible frame' % name)

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

main = r'''import AppKit

let screen = NSRect(x: 100, y: 50, width: 1680, height: 940)

func near(_ a: NSRect, _ b: NSRect, _ what: String) {
    precondition(abs(a.minX - b.minX) < 0.01 && abs(a.minY - b.minY) < 0.01
                 && abs(a.width - b.width) < 0.01 && abs(a.height - b.height) < 0.01,
                 "\(what): \(a) against \(b)")
}

// Nothing chosen is the whole screen, which is what every installation gets
// until somebody says otherwise.
near(TilingArea.apply(fractions: nil, to: screen), screen, "unset")
near(TilingArea.apply(fractions: [:], to: screen), screen, "empty")

// The three the request named, and their mirrors.
near(TilingArea.apply(fractions: TilingArea.fractions(presetNamed: "Left Two Thirds"), to: screen),
     NSRect(x: 100, y: 50, width: 1120, height: 940), "left two thirds")
near(TilingArea.apply(fractions: TilingArea.fractions(presetNamed: "Right Two Thirds"), to: screen),
     NSRect(x: 660, y: 50, width: 1120, height: 940), "right two thirds")
near(TilingArea.apply(fractions: TilingArea.fractions(presetNamed: "Left Half"), to: screen),
     NSRect(x: 100, y: 50, width: 840, height: 940), "left half")
near(TilingArea.apply(fractions: TilingArea.fractions(presetNamed: "Right Half"), to: screen),
     NSRect(x: 940, y: 50, width: 840, height: 940), "right half")
near(TilingArea.apply(fractions: TilingArea.fractions(presetNamed: "Top Half"), to: screen),
     NSRect(x: 100, y: 520, width: 1680, height: 470), "top half")
near(TilingArea.apply(fractions: TilingArea.fractions(presetNamed: "Whole Screen"), to: screen),
     screen, "whole screen")

// Whatever is chosen, the area stays inside the screen: that is the whole point
// of reserving the rest for something else.
for name in TilingArea.presetNames {
    let area = TilingArea.apply(fractions: TilingArea.fractions(presetNamed: name), to: screen)
    precondition(screen.contains(area), "\(name) leaves the screen: \(area)")
}

// A rectangle written so that it runs off the right is brought back, and keeps
// its size, rather than being clipped to a sliver.
near(TilingArea.apply(fractions: ["x": 0.75, "width": 0.5], to: screen),
     NSRect(x: 940, y: 50, width: 840, height: 940), "off the right")

// Out-of-range and nonsense fractions do not produce an out-of-range rectangle.
near(TilingArea.apply(fractions: ["x": -3, "y": -2, "width": 4, "height": 9], to: screen),
     screen, "clamped")
precondition(screen.contains(TilingArea.apply(fractions: ["x": .init(value: Double.nan),
                                                          "width": .init(value: Double.infinity)],
                                              to: screen)))

// An area too small to tile into is refused, and the screen answers whole: a
// viewer 40 points wide helps nobody.
near(TilingArea.apply(fractions: ["width": 0.02], to: screen), screen, "too narrow")
near(TilingArea.apply(fractions: ["height": 0.02], to: screen), screen, "too short")
// And the boundary is where it says it is.
let tall = NSRect(x: 0, y: 0, width: 1000, height: 1000)
precondition(TilingArea.apply(fractions: ["width": 0.32], to: tall).width == 320)   // 320 is allowed
precondition(TilingArea.apply(fractions: ["width": 0.319], to: tall).width == 1000) // 319 is not

// The menu ticks the preset a screen is on, and nothing when the region is one
// the presets do not name.
precondition(TilingArea.presetNames.first == "Whole Screen")
precondition(TilingArea.equal(TilingArea.fractions(presetNamed: "Whole Screen"), nil))
precondition(!TilingArea.equal(TilingArea.fractions(presetNamed: "Left Half"),
                               TilingArea.fractions(presetNamed: "Right Half")))

// A preference spelled with strings - which is what an old-style plist and a
// launch argument give - means the same as one spelled with numbers.
let asText = TilingArea.numbers(from: ["x": "0", "y": "0", "width": "0.5", "height": "1"])
near(TilingArea.apply(fractions: asText, to: screen),
     TilingArea.apply(fractions: TilingArea.fractions(presetNamed: "Left Half"), to: screen),
     "written as text")
precondition(TilingArea.numbers(from: ["width": "not a number"]).isEmpty)
precondition(TilingArea.numbers(from: ["width": NSNumber(value: 0.5)]).count == 1)

print("PASS: the area stays inside the screen, keeps its size, and refuses to be useless")
'''

with tempfile.TemporaryDirectory(prefix='horos-tiling-area-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    build = subprocess.run(['swiftc', str(root / 'Horos/Sources/TilingArea.swift'),
                            str(p / 'main.swift'), '-o', str(p / 'test')],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2000:])
        sys.exit('the tiling area did not compile')
    checks = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    print((checks.stdout + checks.stderr).strip())
    if checks.returncode:
        failures.append('the tiling area does not stay inside the screen it is given')

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: Horos tiles inside the area chosen for each screen')
