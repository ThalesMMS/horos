#!/usr/bin/env python3
"""#380/A300: the same-patient row background is a background, not a text colour.

A300, absorbed from #300: a long patient/study list must not gain **black areas
covering names** while scrolling, selecting or resizing, in light and dark and on
Retina.

`-[BrowserController outlineView:willDisplayCell:...]` fills the name cell when
`displaySamePatientWithColorBackground` is on and the row above is the same
patient. It filled it with `disabledControlTextColor` — a **text** colour. That
is pure black at 25 % alpha in Aqua and pure white at 25 % in Dark Aqua, so the
band over consecutive studies of one patient is literally black, and its mirror
in dark mode. The commented-out original beside it was
`secondarySelectedControlColor`, an actual row background.

This resolves the colour the shipped code names — parsed out of the source, so
the test measures what runs — and requires it to stay readable behind text in
both appearances.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
block = re.search(r'\[cell setDrawsBackground: YES\];(.*?)\n\s*\}', browser, re.S)
if not block:
    failures.append('the same-patient background is no longer set in BrowserController.m')
    colour = None
else:
    named = re.search(r'setBackgroundColor:\s*\[NSColor (\w+)\]', block.group(1))
    if not named:
        failures.append('the same-patient background no longer names an NSColor')
        colour = None
    else:
        colour = named.group(1)

# Text colours are not backgrounds. These are the ones a reader could reach for.
TEXT_COLOURS = {
    'disabledControlTextColor', 'textColor', 'labelColor', 'secondaryLabelColor',
    'tertiaryLabelColor', 'quaternaryLabelColor', 'controlTextColor',
    'selectedTextColor', 'headerTextColor', 'blackColor',
}
if colour in TEXT_COLOURS:
    failures.append('%s is a text colour, not a background' % colour)

cell = (root / 'Horos/Sources/ImageAndTextCell.m').read_bytes().decode('latin1')
if cell.count('[self drawsBackground] && [self backgroundColor]') != 2:
    failures.append('ImageAndTextCell must not fill with a nil background colour; a nil colour '
                    'leaves whatever the context had, which is black')
if cell.count('NSRectFillUsingOperation') != 2:
    failures.append('ImageAndTextCell must blend the background instead of overwriting alpha')
if re.search(r'\n\s*NSRectFill\(imageFrame\);', cell):
    failures.append('ImageAndTextCell still uses NSRectFill, which writes alpha rather than blending')

if colour and not failures:
    driver = ('''
import AppKit

@main struct Check {
    static func main() {
        let background = NSColor.%s
        var worst = 1.0
        for appearance in [NSAppearance(named: .aqua)!, NSAppearance(named: .darkAqua)!] {
            appearance.performAsCurrentDrawingAppearance {
                let b = background.usingColorSpace(.deviceRGB)!
                let t = NSColor.textColor.usingColorSpace(.deviceRGB)!
                func luma(_ c: NSColor) -> Double {
                    0.2126 * c.redComponent + 0.7152 * c.greenComponent + 0.0722 * c.blueComponent
                }
                // A text colour used as a background is opaque-ish black or white
                // and sits right on top of the text: the contrast collapses.
                let separation = abs(luma(b) - luma(t))
                print(String(format: "%%@: background luma %%.3f alpha %%.3f, text luma %%.3f, separation %%.3f",
                             appearance.name.rawValue, luma(b), b.alphaComponent, luma(t), separation))
                worst = min(worst, separation)
                // A row background has to be opaque, or the row beneath shows
                // through and the band changes with what is under it.
                precondition(b.alphaComponent > 0.99, "the row background is translucent")
            }
        }
        precondition(worst > 0.4, "text would not read against this background: \\(worst)")
        print(String(format: "separation at least %%.3f in both appearances", worst))
    }
}
''' % colour)
    with tempfile.TemporaryDirectory(prefix='horos-row-background-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(path / 'Check.swift'),
                                '-o', str(path / 'check')], capture_output=True, text=True)
        if build.returncode:
            failures.append('cannot resolve NSColor.%s: %s' % (colour, build.stderr.strip()[-300:]))
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            print(run.stdout.strip())
            if run.returncode:
                failures.append('%s does not read as a row background: %s'
                                % (colour, run.stderr.strip()[-300:]))

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: the same-patient row uses %s, opaque and readable in light and dark' % colour)
