#!/usr/bin/env python3
"""Projection versus 3D distance for points on distinct slices, in patient mm."""
from pathlib import Path
import math
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
import simd

func close(_ a: Double, _ b: Double, _ e: Double = 1e-9) {
    precondition(a.isFinite && b.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

func axial(_ x: Double, _ y: Double, originZ: Double,
           spacingX: Double = 1, spacingY: Double = 1,
           pixelCenter: Bool = false) -> ROISlicePoint {
    ROISlicePoint(pixelX: x, pixelY: y,
                  originX: 0, originY: 0, originZ: originZ,
                  rowX: 1, rowY: 0, rowZ: 0,
                  colX: 0, colY: 1, colZ: 0,
                  normalX: 0, normalY: 0, normalZ: 1,
                  spacingX: spacingX, spacingY: spacingY,
                  pixelCenter: pixelCenter)
}

// Phantom 1 — parallel axials, known coordinates, pixel centres.
// A (10.5, 0.5) on z=0 and B (10.5, 20.5) on z=5 become (10,0,0) and (10,20,5) mm.
let a1 = axial(10.5, 0.5, originZ: 0, pixelCenter: true)
let b1 = axial(10.5, 20.5, originZ: 5, pixelCenter: true)
let m1 = ROIIntersliceGeometry.measure(from: a1, to: b1)!
close(m1.firstX, 10); close(m1.firstY, 0); close(m1.firstZ, 0)
close(m1.secondX, 10); close(m1.secondY, 20); close(m1.secondZ, 5)
close(m1.projectedDistance, 20)
close(m1.distance3D, sqrt(425))
close(m1.throughPlaneOffset, 5)
precondition(m1.projectedDistance != m1.distance3D)
precondition(m1.unit == "mm")
precondition(m1.orientation == "axial")
precondition(m1.slicesParallel)
precondition(m1.summary.contains("mm"))
precondition(m1.summary.contains("proj"))
precondition(m1.summary.contains("3D"))
precondition(m1.summary.contains("axial"))

// Same in-plane points: 3D is only the slice offset; projection is zero.
let same = ROIIntersliceGeometry.measure(from: a1, to: axial(10.5, 0.5, originZ: 5, pixelCenter: true))!
close(same.projectedDistance, 0)
close(same.distance3D, 5)

// Phantom 2 — anisotropic pixels, no pixel-centre shift.
// A (0,0) @ z=0 → (0,0,0); B (10,5) @ z=4 with 0.5×2 mm → (5,10,4).
let a2 = axial(0, 0, originZ: 0, spacingX: 0.5, spacingY: 2)
let b2 = axial(10, 5, originZ: 4, spacingX: 0.5, spacingY: 2)
let m2 = ROIIntersliceGeometry.measure(from: a2, to: b2)!
close(m2.projectedDistance, hypot(5, 10))
close(m2.distance3D, hypot(hypot(5, 10), 4))
close(m2.throughPlaneOffset, 4)

// Phantom 3 — coronal slices (row +X, col −Z, normal +Y). Projection drops Y.
let coronalA = ROISlicePoint(pixelX: 4, pixelY: 2,
                             originX: 0, originY: 10, originZ: 0,
                             rowX: 1, rowY: 0, rowZ: 0,
                             colX: 0, colY: 0, colZ: -1,
                             normalX: 0, normalY: 1, normalZ: 0,
                             spacingX: 1, spacingY: 1, pixelCenter: false)
let coronalB = ROISlicePoint(pixelX: 10, pixelY: 2,
                             originX: 0, originY: 25, originZ: 0,
                             rowX: 1, rowY: 0, rowZ: 0,
                             colX: 0, colY: 0, colZ: -1,
                             normalX: 0, normalY: 1, normalZ: 0,
                             spacingX: 1, spacingY: 1, pixelCenter: false)
let m3 = ROIIntersliceGeometry.measure(from: coronalA, to: coronalB)!
close(m3.firstX, 4); close(m3.firstY, 10); close(m3.firstZ, -2)
close(m3.secondX, 10); close(m3.secondY, 25); close(m3.secondZ, -2)
close(m3.projectedDistance, 6)
close(m3.distance3D, hypot(6, 15))
precondition(m3.orientation == "coronal")
precondition(m3.slicesParallel)

// Sagittal: row +Y, col +Z, normal +X.
let sagA = ROISlicePoint(pixelX: 0, pixelY: 0,
                         originX: 3, originY: 0, originZ: 0,
                         rowX: 0, rowY: 1, rowZ: 0,
                         colX: 0, colY: 0, colZ: 1,
                         normalX: 1, normalY: 0, normalZ: 0,
                         spacingX: 1, spacingY: 1, pixelCenter: false)
let sagB = ROISlicePoint(pixelX: 8, pixelY: 0,
                         originX: 11, originY: 0, originZ: 0,
                         rowX: 0, rowY: 1, rowZ: 0,
                         colX: 0, colY: 0, colZ: 1,
                         normalX: 1, normalY: 0, normalZ: 0,
                         spacingX: 1, spacingY: 1, pixelCenter: false)
let m4 = ROIIntersliceGeometry.measure(from: sagA, to: sagB)!
close(m4.projectedDistance, 8)
close(m4.distance3D, hypot(8, 8))
precondition(m4.orientation == "sagittal")

// DCMPix fallback when the stored normal is zero: x*sx, y*sy, originZ.
let raw = ROISlicePoint(pixelX: 3, pixelY: 4,
                        originX: 1, originY: 2, originZ: 7,
                        rowX: 0, rowY: 0, rowZ: 0,
                        colX: 0, colY: 0, colZ: 0,
                        normalX: 0, normalY: 0, normalZ: 0,
                        spacingX: 2, spacingY: 0.5, pixelCenter: false)
let p = ROIIntersliceGeometry.patientPoint(from: raw)
close(p.x, 7); close(p.y, 4); close(p.z, 7)

// Zero spacing follows the ROILineGeometry rule (1 mm/pixel).
let unit = axial(4, 0, originZ: 0, spacingX: 0, spacingY: 0)
let pUnit = ROIIntersliceGeometry.patientPoint(from: unit)
close(pUnit.x, 4); close(pUnit.y, 0)

// Degenerate / non-finite inputs.
precondition(ROIIntersliceGeometry.measure(from: a1, to: a1) == nil)
precondition(ROIIntersliceGeometry.measure(
    from: axial(Double.nan, 0, originZ: 0), to: b1) == nil)

// Patient-space measure reuses the same 3D length as VRMeasurementGeometry arms.
let fromPatient = ROIIntersliceGeometry.measure(
    fromX: 0, y: 0, z: 0, toX: 3, y: 4, z: 12,
    planeNormalX: 0, planeNormalY: 0, planeNormalZ: 1)!
close(fromPatient.distance3D, 13)
close(fromPatient.projectedDistance, 5)

print("PASS: projection vs 3D on axial/coronal/sagittal phantoms; mm and orientation explicit")
'''
with tempfile.TemporaryDirectory(prefix='horos-roi-interslice-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/VRMeasurementGeometry.swift'),
        str(root / 'Horos/Sources/ROILineGeometry.swift'),
        str(root / 'Horos/Sources/ROIIntersliceGeometry.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
