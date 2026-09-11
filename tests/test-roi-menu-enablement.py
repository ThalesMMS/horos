#!/usr/bin/env python3
"""Brush merge enablement must not depend on selection order (#373, A255).

A255 asks that selecting a viewer, a series and a ROI produce predictable
enablement, and that a mode which does not apply be refused explicitly rather
than by enabling everything. `-[ViewerController validateMenuItem:]` walked the
selection for `mergeBrushROI:` assigning the answer on every element, so only
the **last** one decided: a brush followed by a polygon disabled the command,
the same two the other way round enabled it, and the merge then ran over a ROI
that is not a brush.

This compiles the shipped rule and requires the answer to be the same for every
ordering of the same selection, and to be true only when every selected ROI is
a brush.
"""
from pathlib import Path
import itertools
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/ROIMenuEnablement.swift'
assert source.is_file(), 'FAIL: ROIMenuEnablement.swift is missing'

# The shipped call site has to use the rule, not a local loop.
viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
start = viewer.index('@selector(mergeBrushROI:))')
block = viewer[start:viewer.index('else if(', start + 10)]
failures = []
if 'HorosROIMenuEnablement' not in block:
    failures.append('validateMenuItem: no longer asks HorosROIMenuEnablement about the brush merge')
if 'valid = YES' in block or 'valid = NO' in block:
    failures.append('validateMenuItem: still assigns the answer inside a loop over the selection')

driver = r'''
import Foundation

@main struct Check {
    static let brush = ROIMenuEnablement.brushToolMode
    static let polygon = 11   // tCPolygon
    static let oval = 9       // tOval

    static func may(_ types: [Int]) -> Bool {
        ROIMenuEnablement.mayMergeBrushROIs(types: types.map { NSNumber(value: $0) })
    }

    static func main() {
        precondition(!may([]), "an empty selection cannot be merged")
        precondition(may([brush]))
        precondition(may([brush, brush, brush]))
        precondition(!may([polygon]))
        precondition(!may([brush, polygon]))
        precondition(!may([polygon, brush]), "the old loop enabled exactly this")

        // Every ordering of the same selection has to give the same answer.
        for selection in [[brush, polygon], [brush, brush, oval], [oval, brush, polygon, brush]] {
            let answers = Set(selection.permutations().map { may($0) })
            precondition(answers.count == 1, "order changed the answer for \(selection)")
            precondition(answers.first == false)
        }
        for selection in [[brush], [brush, brush], [brush, brush, brush]] {
            let answers = Set(selection.permutations().map { may($0) })
            precondition(answers == [true])
        }

        print("PASS: #373 A255 brush merge enablement is true only for an all-brush selection, "
              + "and never depends on the order it was selected in")
    }
}

extension Array {
    func permutations() -> [[Element]] {
        guard count > 1 else { return [self] }
        var result: [[Element]] = []
        for (index, element) in enumerated() {
            var rest = self
            rest.remove(at: index)
            for tail in rest.permutations() { result.append([element] + tail) }
        }
        return result
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-roi-menu-enablement-') as folder:
    directory = Path(folder)
    (directory / 'Check.swift').write_text(driver)
    built = subprocess.run(['xcrun', 'swiftc', '-O', str(source), str(directory / 'Check.swift'),
                            '-o', str(directory / 'check')], capture_output=True, text=True)
    if built.returncode != 0:
        print(built.stderr or built.stdout, file=sys.stderr)
        raise SystemExit(built.returncode)
    run = subprocess.run([str(directory / 'check')], capture_output=True, text=True)
    sys.stdout.write(run.stdout)
    if run.returncode != 0:
        sys.stderr.write(run.stderr)
        failures.append('the rule failed its own checks')

if failures:
    for failure in failures:
        print('FAIL: %s' % failure, file=sys.stderr)
    raise SystemExit(1)
