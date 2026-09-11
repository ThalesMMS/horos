#!/usr/bin/env python3
"""#373/A294: the syncro index modes, in one place and answered the same way.

`-[DCMView sync:]` maps the key viewer's slice onto its own. The two index
formulas -- absolute and ratio -- were written out **four** times in that method,
twice for volumic series and twice again in the fallback for non-volumic ones.
Four copies of one rule is how two of them end up different.

`HorosSyncSeriesIndex` is the single answer. This checks it, and checks that the
method asks it rather than computing again. `syncroLOC`, the default, is not
here: it maps by patient geometry, not by index.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/SyncSeriesIndex.swift'
if not source.is_file():
    failures.append('Horos/Sources/SyncSeriesIndex.swift is missing')
else:
    driver = r'''
import Foundation

@main struct Check {
    static func main() {
        typealias S = SyncSeriesIndex

        // Absolute: the same slice number, counted from the other end when this
        // series is reversed.
        precondition(S.absoluteIndex(position: 3, count: 16, flippedData: false) == 3)
        precondition(S.absoluteIndex(position: 3, count: 16, flippedData: true) == 12)
        precondition(S.absoluteIndex(position: 0, count: 16, flippedData: true) == 15)
        // A longer source than this series: clamped, not out of range.
        precondition(S.absoluteIndex(position: 40, count: 16, flippedData: false) == 15)
        precondition(S.absoluteIndex(position: 40, count: 16, flippedData: true) == 0)
        precondition(S.absoluteIndex(position: 0, count: 0, flippedData: false) == S.noIndex)

        // Ratio: the same fraction of the way through. Equal lengths must be the
        // identity, or synchronising two copies of a series would drift.
        for position in 0..<16 {
            precondition(S.ratioIndex(position: position, sourceCount: 16, count: 16,
                                      flippedData: false) == position)
        }
        precondition(S.ratioIndex(position: 5, sourceCount: 10, count: 100, flippedData: false) == 50)
        precondition(S.ratioIndex(position: 50, sourceCount: 100, count: 10, flippedData: false) == 5)
        precondition(S.ratioIndex(position: 5, sourceCount: 10, count: 100, flippedData: true) == 49)
        // The divisor used to be unguarded: an empty source gave a NaN and then
        // an undefined conversion to int.
        precondition(S.ratioIndex(position: 3, sourceCount: 0, count: 16, flippedData: false) == S.noIndex)
        precondition(S.ratioIndex(position: 3, sourceCount: 16, count: 0, flippedData: false) == S.noIndex)
        // Never out of range, whatever the two lengths are.
        for sourceCount in [1, 2, 7, 16, 200] {
            for count in [1, 2, 7, 16, 200] {
                for position in [0, sourceCount / 2, sourceCount - 1] {
                    for flipped in [false, true] {
                        let index = S.ratioIndex(position: position, sourceCount: sourceCount,
                                                 count: count, flippedData: flipped)
                        precondition(index >= 0 && index < count)
                    }
                }
            }
        }

        // Relative: move by the same number of slices, in this series' own
        // direction, wrapping once.
        precondition(S.relativeIndex(current: 5, difference: 3, count: 16, flippedData: false) == 8)
        precondition(S.relativeIndex(current: 5, difference: 3, count: 16, flippedData: true) == 2)
        precondition(S.relativeIndex(current: 15, difference: 3, count: 16, flippedData: false) == 2)
        precondition(S.relativeIndex(current: 1, difference: 3, count: 16, flippedData: true) == 14)
        precondition(S.relativeIndex(current: 0, difference: 0, count: 0, flippedData: false) == S.noIndex)

        // One wrap is only enough while the move is shorter than the series.
        // #560 is that; this pins what the rule says about it rather than
        // pretending the hole is not there.
        precondition(S.relativeMoveFitsInOneWrap(difference: 3, count: 16))
        precondition(S.relativeMoveFitsInOneWrap(difference: -15, count: 16))
        precondition(!S.relativeMoveFitsInOneWrap(difference: 16, count: 16))
        precondition(!S.relativeMoveFitsInOneWrap(difference: -100, count: 10))
        precondition(!S.relativeMoveFitsInOneWrap(difference: 0, count: 0))
        // Within one wrap the answer is always a slice of this series.
        for count in [1, 2, 7, 16] {
            for current in 0..<count {
                for difference in -(count - 1)...(count - 1) {
                    for flipped in [false, true] {
                        let index = S.relativeIndex(current: current, difference: difference,
                                                    count: count, flippedData: flipped)
                        precondition(index >= 0 && index < count)
                    }
                }
            }
        }

        print("rule ok")
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='horos-sync-index-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                                str(path / 'Check.swift'), '-o', str(path / 'check')],
                               capture_output=True, text=True)
        if build.returncode:
            failures.append('the rule does not compile: %s' % build.stderr.strip().splitlines()[-3:])
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            if run.returncode:
                failures.append('the rule does not answer: %s' % run.stderr.strip())

view = (root / 'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
body = re.search(r'-\(void\) sync:\(NSNotification\*\)note\s*\{(.*?)\n\}\n\n', view, re.S)
if not body:
    failures.append('-[DCMView sync:] is gone')
else:
    text = body.group(1)
    if text.count('HorosSyncSeriesIndex') < 4:
        failures.append('sync: must ask HorosSyncSeriesIndex in every index mode, including the '
                        'non-volumic fallback')
    # The formulas must not come back. These are the exact shapes that were there.
    if re.search(r'ratio\s*\*\s*\(float\)\s*\[dcmPixList count\]', text):
        failures.append('sync: computes the ratio mapping again')
    if re.search(r'newImage\s*[+-]=\s*diff', text):
        failures.append('sync: computes the relative mapping again')
    if re.search(r'newImage\s*=\s*\(long\)\[dcmPixList count\]\s*-1\s*-pos', text):
        failures.append('sync: computes the absolute mapping again')
    # And every mode has to still be reachable.
    for mode in ('syncroABS', 'syncroRatio', 'syncroREL', 'syncroLOC'):
        if mode not in text:
            failures.append('sync: no longer handles %s' % mode)

header = (root / 'Horos/Sources/DCMView.h').read_bytes().decode('latin1')
if 'syncroOFF = 0, syncroABS = 1, syncroREL = 2, syncroLOC = 3, syncroRatio = 4' not in header:
    failures.append('the syncro modes changed; the rule above names them by their old meaning')

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'SyncSeriesIndex.swift in Sources' not in project:
    failures.append('SyncSeriesIndex.swift is not compiled into the Horos target')

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: one rule for the syncro index modes, asked for in all four places, '
      'never out of range, and #560 stated rather than hidden')
