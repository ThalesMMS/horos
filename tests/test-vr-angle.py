#!/usr/bin/env python3
"""Patient-space 3D angle on a known phantom, including rigid camera/volume rotation."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
import Foundation
import simd

func close(_ a: Double, _ b: Double, _ e: Double = 1e-9) {
    precondition(a.isFinite && abs(a - b) < e, "\(a) != \(b)")
}

func angle(_ v: SIMD3<Double>, _ a: SIMD3<Double>, _ b: SIMD3<Double>) -> Double {
    VRMeasurementGeometry.angleDegrees(atX: v.x, y: v.y, z: v.z,
                                       armAX: a.x, armAY: a.y, armAZ: a.z,
                                       armBX: b.x, armBY: b.y, armBZ: b.z)
}

func rotate(_ p: SIMD3<Double>, axis: SIMD3<Double>, degrees: Double) -> SIMD3<Double> {
    let u = simd_normalize(axis)
    let r = degrees * .pi / 180
    return p * cos(r) + simd_cross(u, p) * sin(r) + u * simd_dot(u, p) * (1 - cos(r))
}

// Known phantoms in patient millimetres.
close(angle(SIMD3(0, 0, 0), SIMD3(10, 0, 0), SIMD3(0, 10, 0)), 90)
close(angle(SIMD3(0, 0, 0), SIMD3(3, 0, 0), SIMD3(0, 4, 0)), 90) // 3-4-5
close(angle(SIMD3(0, 0, 0), SIMD3(1, 0, 0), SIMD3(1, 1, 0)), 45)
close(angle(SIMD3(0, 0, 0), SIMD3(2, 0, 0), SIMD3(1, sqrt(3), 0)), 60)
close(angle(SIMD3(5, -2, 8), SIMD3(5, -2, 18), SIMD3(5, 8, 8)), 90)

let vertex = SIMD3(2.0, 3.0, -1.0)
let armA = SIMD3(12.0, 3.0, -1.0)
let armB = SIMD3(2.0, 13.0, 4.0)
let expected = angle(vertex, armA, armB)
precondition(expected.isFinite)
for degrees in [15.0, 37.0, 90.0, 180.0, 270.0] {
    for axis in [SIMD3(0.0, 0.0, 1.0), SIMD3(0.0, 1.0, 0.0), SIMD3(1.0, 1.0, 1.0)] {
        let rv = rotate(vertex, axis: axis, degrees: degrees)
        let ra = rotate(armA, axis: axis, degrees: degrees)
        let rb = rotate(armB, axis: axis, degrees: degrees)
        close(angle(rv, ra, rb), expected, 1e-8)
    }
}

precondition(angle(SIMD3(0, 0, 0), SIMD3(0, 0, 0), SIMD3(1, 0, 0)).isNaN)
precondition(angle(SIMD3(0, Double.nan, 0), SIMD3(1, 0, 0), SIMD3(0, 1, 0)).isNaN)
print("PASS: known patient-space phantoms stay constant under camera/volume rotation")
'''
with tempfile.TemporaryDirectory(prefix='horos-vr-angle-') as d:
    p = Path(d)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/VRMeasurementGeometry.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)
