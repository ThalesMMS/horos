#!/usr/bin/env python3
"""Classify isotropic, anisotropic and incomplete CT stacks before Curved MPR."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation

func slices(_ start: Double, _ step: Double, _ count: Int) -> [NSNumber] {
    (0..<count).map { NSNumber(value: start + Double($0) * step) }
}

func expect(_ got: String, _ want: String) {
    precondition(got == want, "\(got) != \(want)")
}

// Shared volume-geometry numbers (tools/generate-volume-geometry-fixture.py).
let regular = slices(0, 2, 16)
expect(CurvedMPRPathSession.diagnoseVolume(
    pixelSpacingX: 0.5, spacingY: 0.5, slicePositions: regular, orientationCount: 1),
       "anisotropic")

var gapped = slices(0, 2, 16)
gapped.remove(at: 8) // drop the middle slice: 2 mm becomes 4 mm
expect(CurvedMPRPathSession.diagnoseVolume(
    pixelSpacingX: 0.5, spacingY: 0.5, slicePositions: gapped, orientationCount: 1),
       "incomplete")

expect(CurvedMPRPathSession.diagnoseVolume(
    pixelSpacingX: 0.5, spacingY: 0.5, slicePositions: regular, orientationCount: 2),
       "invalid")

// Isotropic CT: in-plane pixel and slice interval are the same 1 mm.
expect(CurvedMPRPathSession.diagnoseVolume(
    pixelSpacingX: 1, spacingY: 1, slicePositions: slices(0, 1, 16), orientationCount: 1),
       "isotropic")

let tiltedKept = slices(0, 2, 16)
let invalid = CurvedMPRPathSession.diagnoseVolume(
    pixelSpacingX: 0.5, spacingY: 0.5, slicePositions: tiltedKept, orientationCount: 2)
expect(invalid, "invalid")
precondition(tiltedKept.count == 16, "invalid volume keeps its slice list")

print("PASS: isotropic, anisotropic, incomplete and invalid stacks keep a phase")
'''
with tempfile.TemporaryDirectory(prefix='horos-curved-mpr-volume-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/CurvedMPRPath.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
