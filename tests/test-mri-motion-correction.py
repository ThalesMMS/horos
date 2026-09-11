#!/usr/bin/env python3
"""Integer in-plane MRI motion on a disk phantom is recovered, and fbrain is not adopted."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func close(_ a: Double, _ b: Double, _ e: Double = 1e-9) {
    precondition(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

let truth: [(Double, Double)] = [(0, 0), (3, -2), (5, 1), (-4, 3), (2, 2)]
let slices = MRIMotionPhantom.diskStack(
    width: 32, height: 32, radius: 7,
    centerX: 15, centerY: 15,
    shifts: truth.map { [$0.0, $0.1] },
    spacing: 1.25,
    foreground: 1000, background: 40)

let report = MRIMotionCorrection.correct(
    slices: slices, referenceIndex: 0, searchRadius: 8, expected: truth)!
precondition(report.method == "ncc-integer")
precondition(report.referenceIndex == 0)
precondition(report.searchRadius == 8)
precondition(report.adopted == false)
precondition(report.shifts.count == truth.count)
precondition(report.elapsedMilliseconds >= 0)
precondition(report.limitation.contains("slice-to-volume") ||
             report.limitation.contains("SVR") ||
             report.limitation.contains("fbrain"))
close(report.meanAbsErrorPixels, 0)
close(report.meanResidualSSD, 0, 1e-6)

for (index, expected) in truth.enumerated() {
    let shift = report.shifts[index]
    close(shift.dxPixels, expected.0)
    close(shift.dyPixels, expected.1)
    close(shift.dxMillimetres, expected.0 * 1.25)
    close(shift.dyMillimetres, expected.1 * 1.25)
    close(shift.peakNCC, 1, 1e-9)
    close(shift.residualSSD, 0, 1e-6)
    precondition(shift.reliable)
}

// No motion: every slice matches the reference.
let still = MRIMotionPhantom.diskStack(
    width: 24, height: 24, radius: 5,
    centerX: 11, centerY: 11,
    shifts: [[0, 0], [0, 0], [0, 0]],
    spacing: 1, foreground: 800, background: 10)
let identity = MRIMotionCorrection.correct(
    slices: still, referenceIndex: 0, searchRadius: 4, expected: [(0, 0), (0, 0), (0, 0)])!
close(identity.meanAbsErrorPixels, 0)
precondition(identity.shifts.allSatisfy { $0.dxPixels == 0 && $0.dyPixels == 0 && $0.reliable })

// Motion larger than the search window is reported, not guessed as adopted.
let far = MRIMotionPhantom.diskStack(
    width: 32, height: 32, radius: 6,
    centerX: 15, centerY: 15,
    shifts: [[0, 0], [10, 0]],
    spacing: 1, foreground: 900, background: 20)
let clipped = MRIMotionCorrection.correct(
    slices: far, referenceIndex: 0, searchRadius: 3)!
precondition(clipped.shifts[1].reliable == false)
precondition(abs(clipped.shifts[1].dxPixels - 10) > 0.5)
precondition(clipped.adopted == false)

precondition(MRIMotionCorrection.correct(slices: [], referenceIndex: 0, searchRadius: 4) == nil)
precondition(MRIMotionCorrection.correct(slices: slices, referenceIndex: 9, searchRadius: 4) == nil)
precondition(MRIMotionCorrection.correct(slices: slices, referenceIndex: 0, searchRadius: 0) == nil)

let bad = MRIMotionSlice(width: 2, height: 2, pixels: [1, 2, 3], spacingX: 1, spacingY: 1)
precondition(MRIMotionCorrection.correct(slices: [bad], referenceIndex: 0, searchRadius: 1) == nil)

let nanPix = MRIMotionSlice(width: 1, height: 1, pixels: [Double.nan], spacingX: 1, spacingY: 1)
precondition(MRIMotionCorrection.correct(slices: [nanPix], referenceIndex: 0, searchRadius: 1) == nil)

print("PASS: disk phantom translations recovered; fbrain not adopted")
'''
source = root / 'Horos/Sources/MRIMotionCorrection.swift'
if not source.is_file():
    raise SystemExit('FAIL: MRIMotionCorrection.swift is missing')
with tempfile.TemporaryDirectory(prefix='horos-mri-motion-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(source), str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
