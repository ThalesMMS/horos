#!/usr/bin/env python3
"""Analytical ROI volume from ImagePositionPatient, not SpacingBetweenSlices."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
import simd

func close(_ a: Double, _ b: Double, _ e: Double = 1e-9) {
    precondition(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

func axial(_ area: Double, z: Double, components: Int = 1,
           maskPixels: Int = 0, pixelArea: Double = 0,
           spacingBetweenSlices: Double = 2) -> ROIVolumeSlice {
    ROIVolumeSlice(areaCm2: area,
                   originX: 0, originY: 0, originZ: z,
                   normalX: 0, normalY: 0, normalZ: 1,
                   componentCount: components,
                   maskPixelCount: maskPixels,
                   pixelAreaMm2: pixelArea,
                   spacingBetweenSlicesMm: spacingBetweenSlices)
}

func origin(x: Double = 0, y: Double = 0, z: Double) -> ROIPatientPoint {
    ROIPatientPoint(x: x, y: y, z: z)
}

// Phantom 1 — regular prism. Three 10 cm² ROIs at z = 0, 5, 10 mm.
// Host trapezoid in cm: two intervals of 0.5 cm × 10 cm² = 10 cm³.
let regular = [axial(10, z: 0), axial(10, z: 5), axial(10, z: 10)]
let seriesRegular = [origin(z: 0), origin(z: 5), origin(z: 10)]
let r1 = ROIVolumeGeometry.volume(from: regular, seriesOrigins: seriesRegular,
                                  interpolateMissing: false, meshPointCount: 0)!
close(r1.volumeCm3, 10)
precondition(r1.unit == "cm3")
precondition(r1.method == "physical-trapezoid")
precondition(r1.usedImagePositionPatient)
precondition(!r1.usedSpacingBetweenSlices)
precondition(r1.occupiedPlaneCount == 3)
precondition(r1.gapCount == 0)
precondition(!r1.interpolated)
precondition(r1.componentCount == 3)
precondition(r1.maskConsistent)
precondition(r1.summary.contains("cm3"))

// Same IPP, SpacingBetweenSlices 99 mm must not change the volume.
let lying = regular.map {
    axial($0.areaCm2, z: $0.originZ, spacingBetweenSlices: 99)
}
let rLie = ROIVolumeGeometry.volume(from: lying, seriesOrigins: seriesRegular,
                                    interpolateMissing: false, meshPointCount: 0)!
close(rLie.volumeCm3, r1.volumeCm3)

// Index × SpacingBetweenSlices (the old host location) is not the proof.
let fakeInterval = 99.0
var indexVolume = 0.0, prev = 0.0, pre = 0.0
for (i, slice) in lying.enumerated() {
    let loc = Double(i) * fakeInterval
    if i > 0 { indexVolume += ((loc - pre) / 10) * (slice.areaCm2 + prev) / 2 }
    prev = slice.areaCm2
    pre = loc
}
precondition(abs(indexVolume - r1.volumeCm3) > 1)

// Phantom 2 — irregular physical intervals: 0, 2, 8 mm, area 10 cm².
let uneven = [axial(10, z: 0), axial(10, z: 2), axial(10, z: 8)]
let r2 = ROIVolumeGeometry.volume(from: uneven,
                                  seriesOrigins: [origin(z: 0), origin(z: 2), origin(z: 8)],
                                  interpolateMissing: false, meshPointCount: 0)!
close(r2.volumeCm3, 8)
precondition(r2.gapCount == 0)

// Phantom 3 — gap. Series 0, 5, 10, 15 mm; ROIs only at 0 and 15.
let gapped = [axial(10, z: 0), axial(10, z: 15)]
let seriesGap = [0.0, 5.0, 10.0, 15.0].map { origin(z: $0) }
let rGap = ROIVolumeGeometry.volume(from: gapped, seriesOrigins: seriesGap,
                                    interpolateMissing: false, meshPointCount: 0)!
close(rGap.volumeCm3, 0)
precondition(rGap.gapCount == 1)
precondition(!rGap.interpolated)

let rFill = ROIVolumeGeometry.volume(from: gapped, seriesOrigins: seriesGap,
                                     interpolateMissing: true, meshPointCount: 0)!
close(rFill.volumeCm3, 15)
precondition(rFill.gapCount == 1)
precondition(rFill.interpolated)

// Two contiguous runs with a hole between them: 0–5 and 15–20.
let runs = [axial(10, z: 0), axial(10, z: 5), axial(10, z: 15), axial(10, z: 20)]
let seriesRuns = [0.0, 5.0, 10.0, 15.0, 20.0].map { origin(z: $0) }
let rRuns = ROIVolumeGeometry.volume(from: runs, seriesOrigins: seriesRuns,
                                     interpolateMissing: false, meshPointCount: 0)!
close(rRuns.volumeCm3, 10)
precondition(rRuns.gapCount == 1)
precondition(!rRuns.interpolated)

// Phantom 4 — disconnected components on the same planes (areas summed, never unioned).
let split = [axial(3 + 5, z: 0, components: 2), axial(3 + 5, z: 10, components: 2)]
let rSplit = ROIVolumeGeometry.volume(from: split,
                                      seriesOrigins: [origin(z: 0), origin(z: 10)],
                                      interpolateMissing: false, meshPointCount: 0)!
close(rSplit.volumeCm3, 8)
precondition(rSplit.componentCount == 4)

// Two slice records on the same plane are one plane, areas added, no fusion.
let samePlane = [
    axial(3, z: 0, components: 1),
    axial(5, z: 0, components: 1),
    axial(8, z: 10, components: 1)
]
let rSame = ROIVolumeGeometry.volume(from: samePlane,
                                     seriesOrigins: [origin(z: 0), origin(z: 10)],
                                     interpolateMissing: false, meshPointCount: 0)!
close(rSame.volumeCm3, 8)
precondition(rSame.occupiedPlaneCount == 2)
precondition(rSame.componentCount == 3)

// Phantom 5 — coronal (normal +Y). IPP y changes; z stays 0. Using z would be 0.
let coronal = [
    ROIVolumeSlice(areaCm2: 10, originX: 0, originY: 0, originZ: 0,
                   normalX: 0, normalY: 1, normalZ: 0, componentCount: 1,
                   maskPixelCount: 0, pixelAreaMm2: 0, spacingBetweenSlicesMm: 99),
    ROIVolumeSlice(areaCm2: 10, originX: 0, originY: 5, originZ: 0,
                   normalX: 0, normalY: 1, normalZ: 0, componentCount: 1,
                   maskPixelCount: 0, pixelAreaMm2: 0, spacingBetweenSlicesMm: 99),
    ROIVolumeSlice(areaCm2: 10, originX: 0, originY: 10, originZ: 0,
                   normalX: 0, normalY: 1, normalZ: 0, componentCount: 1,
                   maskPixelCount: 0, pixelAreaMm2: 0, spacingBetweenSlicesMm: 99)
]
let rCor = ROIVolumeGeometry.volume(from: coronal,
                                    seriesOrigins: [origin(y: 0, z: 0), origin(y: 5, z: 0), origin(y: 10, z: 0)],
                                    interpolateMissing: false, meshPointCount: 0)!
close(rCor.volumeCm3, 10)

// Mask area matches the quantitative area (10×10 px × 1 mm² = 1 cm²).
let masked = [
    axial(1, z: 0, maskPixels: 100, pixelArea: 1),
    axial(1, z: 5, maskPixels: 100, pixelArea: 1)
]
let rMask = ROIVolumeGeometry.volume(from: masked,
                                     seriesOrigins: [origin(z: 0), origin(z: 5)],
                                     interpolateMissing: false, meshPointCount: 0)!
close(rMask.volumeCm3, 0.5)
precondition(rMask.maskConsistent)
let rBadMask = ROIVolumeGeometry.volume(
    from: [axial(1, z: 0, maskPixels: 50, pixelArea: 1),
           axial(1, z: 5, maskPixels: 50, pixelArea: 1)],
    seriesOrigins: [origin(z: 0), origin(z: 5)],
    interpolateMissing: false, meshPointCount: 0)!
precondition(!rBadMask.maskConsistent)

// Mesh point decimation is display-only and must not change the source volume.
let rMesh = ROIVolumeGeometry.volume(from: regular, seriesOrigins: seriesRegular,
                                     interpolateMissing: false, meshPointCount: 7000)!
close(rMesh.volumeCm3, r1.volumeCm3)
precondition(rMesh.meshPointCount == 7000)

// Degenerate inputs.
precondition(ROIVolumeGeometry.volume(from: [axial(10, z: 0)],
                                      seriesOrigins: [origin(z: 0)],
                                      interpolateMissing: false, meshPointCount: 0) == nil)
precondition(ROIVolumeGeometry.volume(
    from: [axial(10, z: 0), axial(Double.nan, z: 5)],
    seriesOrigins: seriesRegular, interpolateMissing: false, meshPointCount: 0) == nil)
precondition(ROIVolumeGeometry.volume(
    from: [axial(0, z: 0), axial(10, z: 5)],
    seriesOrigins: [origin(z: 0), origin(z: 5)],
    interpolateMissing: false, meshPointCount: 0) == nil)

print("PASS: physical trapezoid on regular/uneven/gap/disconnected/coronal phantoms; SBS ignored; mesh unused")
'''
with tempfile.TemporaryDirectory(prefix='horos-roi-volume-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/VRMeasurementGeometry.swift'),
        str(root / 'Horos/Sources/ROILineGeometry.swift'),
        str(root / 'Horos/Sources/ROIIntersliceGeometry.swift'),
        str(root / 'Horos/Sources/ROIVolumeGeometry.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
