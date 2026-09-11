#!/usr/bin/env python3
"""Compute a known dynamic TAC with the native arm64 ROI Enhancement."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/ROIEnhancement.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/ROIEnhancement.swift is missing')

code = r'''
import Foundation

func close(_ a: Double, _ b: Double, _ e: Double = 1e-4) {
    precondition(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

precondition(ROIEnhancement.version == "1.0")
precondition(ROIEnhancement.abi == "arm64-native")
precondition(ROIEnhancement.menuTitle == "ROI Enhancement")
precondition(ROIEnhancement.legacyVersion == "2.3.1")
precondition(ROIEnhancement.legacyPrincipalClass == "ROI_Enhancement_II")
precondition(ROIEnhancement.sourceRevision == "6b4036242ca4f821679bcd83942a4b842d7ffb2c")

let times = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]
let hu = [40.0, 80.0, 150.0, 220.0, 200.0, 140.0, 90.0, 60.0]
let width = 8, height = 8
let vessel = ROIEnhancement.Region(name: "vessel", column: 2, row: 2, width: 4, height: 4)

func frame(_ value: Double) -> [Float] {
    var pixels = [Float](repeating: 0, count: width * height)
    for row in vessel.row..<(vessel.row + vessel.height) {
        for column in vessel.column..<(vessel.column + vessel.width) {
            pixels[row * width + column] = Float(value)
        }
    }
    return pixels
}

let phases = zip(times, hu).map {
    ROIEnhancement.Phase(timeSeconds: $0.0, pixels: frame($0.1), width: width, height: height)
}

let few = ROIEnhancement.curves(phases: Array(phases.prefix(1)), regions: [vessel])
precondition(few.code == ROIEnhancement.ErrorCode.tooFewPhases.rawValue)
precondition(few.reason.contains("dynamic") || few.reason.contains("4D") || few.reason.contains("phase"))

let missing = ROIEnhancement.curves(phases: phases, regions: [])
precondition(missing.code == ROIEnhancement.ErrorCode.missingROI.rawValue)
precondition(missing.reason.contains("ROI"))

let empty = ROIEnhancement.curves(
    phases: [
        ROIEnhancement.Phase(timeSeconds: 0, pixels: [], width: 0, height: 0),
        ROIEnhancement.Phase(timeSeconds: 2, pixels: [], width: 0, height: 0)
    ],
    regions: [vessel])
precondition(empty.code == ROIEnhancement.ErrorCode.emptySeries.rawValue)

let mismatch = ROIEnhancement.curves(
    phases: [
        ROIEnhancement.Phase(timeSeconds: 0, pixels: frame(40), width: width, height: height),
        ROIEnhancement.Phase(timeSeconds: 2, pixels: [1, 2], width: width, height: height)
    ],
    regions: [vessel])
precondition(mismatch.code == ROIEnhancement.ErrorCode.sizeMismatch.rawValue)

let result = ROIEnhancement.curves(phases: phases, regions: [vessel])
precondition(result.code == 0, result.reason)
precondition(result.curves.count == 1)
precondition(result.curves[0].name == "vessel")
precondition(result.curves[0].samples.count == times.count)
for (index, sample) in result.curves[0].samples.enumerated() {
    close(sample.timeSeconds, times[index])
    close(sample.min, hu[index])
    close(sample.mean, hu[index])
    close(sample.max, hu[index])
    precondition(sample.count == vessel.width * vessel.height)
}

let filter = ROIEnhancementFilter()
precondition(filter.prepareFilter(nil) == 0)
precondition(filter.filterImage("ROI Enhancement") == ROIEnhancement.ErrorCode.emptySeries.rawValue)
precondition(filter.lastReason.contains("viewer") || filter.lastReason.contains("phantom"))

filter.prepare(phases: phases, regions: [vessel])
precondition(filter.filterImage("ROI Enhancement") == 0)
precondition(filter.lastCurves.count == 1)
close(filter.lastCurves[0].samples[3].mean, 220)

print("PASS: native ROI Enhancement 1.0 recovers the dynamic phantom TAC and refuses incomplete series")
'''

with tempfile.TemporaryDirectory(prefix='horos-roi-enhancement-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc', str(source), str(path / 'main.swift'),
        '-o', str(path / 'test')
    ], check=True)
    subprocess.run([str(path / 'test')], check=True)
