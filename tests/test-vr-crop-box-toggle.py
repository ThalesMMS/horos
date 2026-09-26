#!/usr/bin/env python3
"""Turning the VR crop box back on shows the crop in place, not the whole volume."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
volume = (root / 'Horos/Sources/VRView.mm').read_bytes().decode('latin1')
toggle = re.search(r'-\(void\) showCropCube:.*?\n}\n', volume, re.S)
if not toggle or 'placeCropBoxOnAppliedCrop' not in toggle.group(0) or 'PlaceWidget' in toggle.group(0):
    print('FAIL: showCropCube: must place the box on the applied crop, not on the whole volume')
    sys.exit(1)

code = r'''
import Foundation
typealias V = [Double]
func n(_ values: [Double]) -> [NSNumber] { values.map(NSNumber.init(value:)) }
func apply(_ m: [Double], _ p: V) -> V {
    (0..<3).map { r in m[r * 4] * p[0] + m[r * 4 + 1] * p[1] + m[r * 4 + 2] * p[2] + m[r * 4 + 3] }
}
func close(_ a: V, _ b: V) -> Bool { zip(a, b).allSatisfy { abs($0 - $1) < 1e-9 } }
// Planes of the box `bounds` moved by rotation R and offset t, in vtkBoxWidget's face order.
func planes(_ bounds: [Double], _ r: [[Double]], _ t: V, inward: Bool) -> ([Double], [Double]) {
    let c = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2]
    var origins: [Double] = [], normals: [Double] = []
    for face in 0..<6 {
        let axis = face / 2, side = face % 2 == 0 ? -1.0 : 1.0
        var p = c; p[axis] = bounds[face]
        var normal = [0.0, 0.0, 0.0]; normal[axis] = inward ? -side : side
        let moved = (0..<3).map { row in (0..<3).reduce(t[row]) { $0 + r[row][$1] * p[$1] } }
        let turned = (0..<3).map { row in (0..<3).reduce(0.0) { $0 + r[row][$1] * normal[$1] } }
        origins += moved; normals += turned
    }
    return (origins, normals)
}
let bounds = [-100.0, 120.0, -80.0, 90.0, 0.0, 250.0]
let identity = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]

// Placed on the whole volume: identity.
var (o, nm) = planes(bounds, identity, [0, 0, 0], inward: true)
var m = VTKRetinaGeometry.cropBoxTransform(planeOrigins: n(o), normals: n(nm), bounds: n(bounds)).map(\.doubleValue)
precondition(m.count == 16 && close(m, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]), "whole volume: \(m)")

// A cropped, rotated and moved box: every corner of the placed box lands on the crop's.
let crop = [-40.0, 60.0, -30.0, 50.0, 20.0, 180.0]
let a = 0.6, b = -0.4
let rz = [[cos(a), -sin(a), 0], [sin(a), cos(a), 0], [0, 0, 1.0]]
let rx = [[1.0, 0, 0], [0, cos(b), -sin(b)], [0, sin(b), cos(b)]]
let r = (0..<3).map { i in (0..<3).map { j in (0..<3).reduce(0.0) { $0 + rz[i][$1] * rx[$1][j] } } }
let t = [12.0, -7.0, 30.0]
(o, nm) = planes(crop, r, t, inward: false)
m = VTKRetinaGeometry.cropBoxTransform(planeOrigins: n(o), normals: n(nm), bounds: n(bounds)).map(\.doubleValue)
precondition(m.count == 16, "rotated crop must give a matrix")
for x in 0..<2 { for y in 0..<2 { for z in 0..<2 {
    let placed = [bounds[x], bounds[2 + y], bounds[4 + z]]
    let cropped = [crop[x], crop[2 + y], crop[4 + z]]
    let expected = (0..<3).map { row in (0..<3).reduce(t[row]) { $0 + r[row][$1] * cropped[$1] } }
    precondition(close(apply(m, placed), expected), "corner \(x)\(y)\(z): \(apply(m, placed)) != \(expected)")
}}}

// A camera saved without a crop holds invalid planes: no matrix, the box stays on the volume.
let zero = [Double](repeating: 0, count: 18)
precondition(VTKRetinaGeometry.cropBoxTransform(planeOrigins: n(zero), normals: n(zero), bounds: n(bounds)).isEmpty)
precondition(VTKRetinaGeometry.cropBoxTransform(planeOrigins: n(o), normals: n(nm), bounds: n([0, 0, 0, 1, 0, 1])).isEmpty)
precondition(VTKRetinaGeometry.cropBoxTransform(planeOrigins: n([.nan] + o.dropFirst()), normals: n(nm), bounds: n(bounds)).isEmpty)
print("PASS: the crop box reappears on the crop in place, rotated or not; invalid planes keep the whole volume")
'''
with tempfile.TemporaryDirectory(prefix='horos-crop-box-') as directory:
    p = Path(directory)
    (p / 'main.swift').write_text(code)
    subprocess.run(['xcrun', 'swiftc',
                    str(root / 'Horos/Sources/VTKRetinaGeometry.swift'),
                    str(root / 'Horos/Sources/VRInteractionGeometry.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
