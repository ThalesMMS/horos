#!/usr/bin/env python3
"""Physical perpendicular, parallel and midpoint for a selected line ROI."""
from pathlib import Path
import math
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit
import Foundation
import simd

func close(_ a: NSPoint, _ b: NSPoint, _ e: CGFloat = 1e-9) {
    precondition(abs(a.x - b.x) < e && abs(a.y - b.y) < e, "\(a) != \(b)")
}

let sx: CGFloat = 0.5, sy: CGFloat = 2
let a = NSPoint(x: 0, y: 0), b = NSPoint(x: 20, y: 10)
let geom = ROILineGeometry.construction(from: a, b: b, spacingX: sx, spacingY: sy)!
close(geom.midpoint, NSPoint(x: 10, y: 5))

let physDotPerp = ROILineGeometry.physicalDotProduct(
    from: a, to: b, otherFrom: geom.perpendicularA, otherTo: geom.perpendicularB,
    spacingX: sx, spacingY: sy)
precondition(abs(physDotPerp) < 1e-9)

let physDotPar = ROILineGeometry.physicalDotProduct(
    from: a, to: b, otherFrom: geom.parallelA, otherTo: geom.parallelB,
    spacingX: sx, spacingY: sy)
let len = hypot(Double((b.x - a.x) * sx), Double((b.y - a.y) * sy))
let parLen = hypot(Double((geom.parallelB.x - geom.parallelA.x) * sx),
                   Double((geom.parallelB.y - geom.parallelA.y) * sy))
let perpLen = hypot(Double((geom.perpendicularB.x - geom.perpendicularA.x) * sx),
                    Double((geom.perpendicularB.y - geom.perpendicularA.y) * sy))
precondition(abs(physDotPar - len * len) < 1e-6)
precondition(abs(parLen - len) < 1e-9)
precondition(abs(perpLen - len) < 1e-9)

// Pixel-space 90° is not the physical perpendicular on this anisotropic line.
let pixelPerpA = NSPoint(x: 5, y: 15), pixelPerpB = NSPoint(x: 15, y: -5)
let pixelDot = ROILineGeometry.physicalDotProduct(
    from: a, to: b, otherFrom: pixelPerpA, otherTo: pixelPerpB, spacingX: sx, spacingY: sy)
precondition(abs(pixelDot) > 1)

close(geom.perpendicularA, NSPoint(x: 30, y: 2.5))
close(geom.perpendicularB, NSPoint(x: -10, y: 7.5))

precondition(ROILineGeometry.construction(from: a, b: a, spacingX: sx, spacingY: sy) == nil)
precondition(ROILineGeometry.construction(
    from: NSPoint(x: CGFloat.nan, y: 0), b: b, spacingX: sx, spacingY: sy) == nil)

let right = ROILineGeometry.physicalAngleDegrees(
    at: NSPoint(x: 0, y: 0), armA: NSPoint(x: 4, y: 0), armB: NSPoint(x: 4, y: 4),
    spacingX: 1, spacingY: 0.5)
precondition(abs(right - (atan(0.5) * 180 / .pi)) < 1e-9)
print("PASS: physical midpoint, parallel, perpendicular; anisotropic pixel 90° rejected; existing angle rule")
'''
with tempfile.TemporaryDirectory(prefix='horos-roi-line-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/VRMeasurementGeometry.swift'),
        str(root / 'Horos/Sources/ROILineGeometry.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
