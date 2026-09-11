#!/usr/bin/env python3
"""A fractional window survives the fields that show and read it."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = r'''import Foundation

// An ordinary window reads as an integer; nothing gains ".000".
assert(WindowLevelText.string(for: 400) == "400")
assert(WindowLevelText.string(for: -1024) == "-1024")
assert(WindowLevelText.string(for: 0) == "0")

// A fractional one keeps its digits, and only as many as it needs.
assert(WindowLevelText.string(for: 0.5) == "0.5")
assert(WindowLevelText.string(for: 1) == "1")
assert(WindowLevelText.string(for: 0.25) == "0.25")
assert(WindowLevelText.string(for: 0.0625) == "0.0625")
assert(WindowLevelText.string(for: -0.5) == "-0.5")
assert(WindowLevelText.string(for: 40.5) == "40.5")
// Beyond four decimals the field rounds rather than growing without limit.
assert(WindowLevelText.string(for: 0.00001) == "0.0000")
assert(WindowLevelText.string(for: Double.nan) == "0")
assert(WindowLevelText.string(for: Double.infinity) == "0")

// Round trip: what the sheet shows is what it reads back.
for value in [0.5, 1.0, 0.25, 400.0, -1024.0, 0.0625, 2047.5, -0.5] {
    let text = WindowLevelText.string(for: value)
    assert(WindowLevelText.value(from: text, fallback: -999) == value, text)
}

// Typing.
assert(WindowLevelText.value(from: "0.5", fallback: -1) == 0.5)
assert(WindowLevelText.value(from: "  40.5  ", fallback: -1) == 40.5)
assert(WindowLevelText.value(from: "0,5", fallback: -1) == 0.5)      // decimal comma
assert(WindowLevelText.value(from: "1.5,5", fallback: -1) == -1)     // not a number
assert(WindowLevelText.value(from: "", fallback: 7) == 7)
assert(WindowLevelText.value(from: "abc", fallback: 7) == 7)
assert(WindowLevelText.value(from: "-1024", fallback: 0) == -1024)

// A width may be fractional but never zero. This is where the old
// intValue-then-guard path turned 0.5 into 1.
assert(WindowLevelText.width(from: "0.5", fallback: 1) == 0.5)
assert(WindowLevelText.width(from: "1", fallback: 99) == 1)
assert(WindowLevelText.width(from: "0", fallback: 99) == 1)
assert(WindowLevelText.width(from: "", fallback: 0) == 1)
assert(WindowLevelText.width(from: "abc", fallback: 0.5) == 0.5)

// The reported case: an image windowed at WL 0.5 / WW 1. Capturing it as a
// preset used to offer "0" and "1" and then apply 0 and 1 to the view.
let level = WindowLevelText.string(for: 0.5)
let width = WindowLevelText.string(for: 1)
assert(level == "0.5" && width == "1")
assert(WindowLevelText.value(from: level, fallback: 0) == 0.5)
assert(WindowLevelText.width(from: width, fallback: 1) == 1)

print("PASS: integers stay integers, fractions survive the round trip, commas parse, width is never zeroed")
'''

sources = {
    'Horos/Sources/ViewerController.m': [
        'AddCurrentWLWW', 'endNameWLWW', 'SetWLWW', 'endSetWLWW', 'updateSetWLWW'],
    'Horos/Sources/MPR2DController.mm': ['AddCurrentWLWW'],
    'Horos/Sources/VRControllerVPRO.mm': ['AddCurrentWLWW'],
    'Horos/Sources/VRController.mm': ['AddCurrentWLWW'],
    'Horos/Sources/Window3DController.m': [
        'endNameWLWW', 'SetWLWW', 'endSetWLWW', 'updateSetWLWW'],
}
# No window field may go back to printing or reading the value as an integer.
for path, methods in sources.items():
    text = (root / path).read_bytes().decode('latin1')
    for method in methods:
        # Anchor on the declaration: -endSetWLWW: contains -SetWLWW: as a suffix.
        declaration = re.search(r'^-\s*\((?:void|IBAction)\)\s*' + method + r':', text, re.M)
        assert declaration, f'{path} has no -{method}:'
        start = declaration.start()
        body = text[start:text.index('\n}', start)]
        assert 'intValue' not in body, f'{path} {method} reads a window as an integer'
        for rounded in ('%0.f', '%.0f', '%d'):
            assert rounded not in body, f'{path} {method} prints a window rounded ({rounded})'
        assert 'HorosWindowLevelText' in body, f'{path} {method} does not use the shared field text'

# The main menu's Set WL/WW manually opened the preset-naming sheet, so setting
# a window without saving a preset was reachable only from the viewer's pop-up.
menu = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
item = menu.index('@"Set WL/WW manually"')
assert 'selector (SetWLWW:)' in menu[item:item + 160], (
    'Set WL/WW manually must open the manual sheet, not the preset sheet')

with tempfile.TemporaryDirectory(prefix='horos-window-level-text-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(main)
    subprocess.run(['swiftc', str(root / 'Horos/Sources/WindowLevelText.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
