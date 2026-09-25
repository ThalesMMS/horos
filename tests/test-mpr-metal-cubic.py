#!/usr/bin/env python3
"""Cubic display interpolation of the Metal reslice against an independent oracle (#702).

The reslicer's `cubic` mode is Catmull-Rom over the 4x4x4 neighbourhood of a
sample, neighbours clamped to the edge as the linear mode clamps them, and the
result kept within the eight voxels a linear sample would use. This test
rebuilds each phantom in Python, reslices the same planes with that formula,
and compares. Tolerances, fixed here before any comparison:

- a plane through voxel centres returns the stored values: 1e-3 (the weights
  there are 0, 1, 0, 0 exactly);
- a linear ramp sampled where all 64 neighbours are inside is reproduced:
  1e-3 (Catmull-Rom is exact on polynomials of degree one);
- a sharp step never leaves the range of its eight surrounding voxels - no
  halo - and is sharper than the linear mode (it departs further from linear
  at the fractional samples);
- any other plane, and the thin slabs the host draws (1 mm, maximum and
  mean): 1e-4 relative to the value range.

The linear mode is the default and is checked by test-mpr-metal-reslicer.py;
here it is only checked to be what a plane asks for when it does not say.
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]


def phantom(i, j, k):
    return float(((i * 7 + j * 3 + k * 11) % 23) * 10 + (i ^ j ^ k))


def ramp(i, j, k):
    return 256.0 + i + 2.0 * j + 3.0 * k


def step(i, j, k):
    return 1000.0 if i >= 6 else 0.0


VOLUMES = {'phantom': phantom, 'ramp': ramp, 'step': step}


def weights(t):
    t2, t3 = t * t, t * t * t
    return [-0.5 * t3 + t2 - 0.5 * t, 1.5 * t3 - 2.5 * t2 + 1.0, -1.5 * t3 + 2.0 * t2 + 0.5 * t, 0.5 * t3 - 0.5 * t2]


def cubic(volume, dims, v):
    for axis in range(3):
        if not (-0.5 <= v[axis] <= dims[axis] - 0.5):
            return None
    base = [math.floor(c) for c in v]
    w = [weights(v[a] - base[a]) for a in range(3)]
    def at(i, j, k):
        return volume(min(max(i, 0), dims[0] - 1), min(max(j, 0), dims[1] - 1), min(max(k, 0), dims[2] - 1))
    total, near = 0.0, []
    for dz in range(4):
        for dy in range(4):
            for dx in range(4):
                c = at(base[0] - 1 + dx, base[1] - 1 + dy, base[2] - 1 + dz)
                total += w[0][dx] * w[1][dy] * w[2][dz] * c
                if dx in (1, 2) and dy in (1, 2) and dz in (1, 2):
                    near.append(c)
    return min(max(total, min(near)), max(near))


def invert(m):
    a = [[m[r][c] for c in range(3)] for r in range(3)]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    inv = [[0.0] * 3 for _ in range(3)]
    inv[0][0] = (a[1][1] * a[2][2] - a[1][2] * a[2][1]) / det
    inv[0][1] = (a[0][2] * a[2][1] - a[0][1] * a[2][2]) / det
    inv[0][2] = (a[0][1] * a[1][2] - a[0][2] * a[1][1]) / det
    inv[1][0] = (a[1][2] * a[2][0] - a[1][0] * a[2][2]) / det
    inv[1][1] = (a[0][0] * a[2][2] - a[0][2] * a[2][0]) / det
    inv[1][2] = (a[0][2] * a[1][0] - a[0][0] * a[1][2]) / det
    inv[2][0] = (a[1][0] * a[2][1] - a[1][1] * a[2][0]) / det
    inv[2][1] = (a[0][1] * a[2][0] - a[0][0] * a[2][1]) / det
    inv[2][2] = (a[0][0] * a[1][1] - a[0][1] * a[1][0]) / det
    t = [m[r][3] for r in range(3)]
    return lambda p: [sum(inv[r][c] * (p[c] - t[c]) for c in range(3)) for r in range(3)]


def oracle(case):
    volume, dims = VOLUMES[case['volume']], case['dims']
    to_voxel = invert(case['voxelToWorld'])
    o, rs, cs = case['origin'], case['rowStep'], case['columnStep']
    n = [rs[1] * cs[2] - rs[2] * cs[1], rs[2] * cs[0] - rs[0] * cs[2], rs[0] * cs[1] - rs[1] * cs[0]]
    length = math.sqrt(sum(c * c for c in n)); n = [c / length for c in n]
    thickness, step = case['thickness'], case['sampleStep']
    count = max(2, math.ceil(thickness / step - 1e-9) + 1) if thickness > 0 else 1
    slab = [n[a] * (thickness / (count - 1)) for a in range(3)] if count > 1 else [0, 0, 0]
    result = []
    for y in range(case['height']):
        for x in range(case['width']):
            centre = [o[a] + x * rs[a] + y * cs[a] for a in range(3)]
            values = [v for v in (cubic(volume, dims, to_voxel([centre[a] + slab[a] * (s - (count - 1) / 2) for a in range(3)]))
                                  for s in range(count)) if v is not None]
            if not values:
                result.append(case['background'])
            elif case['projection'] == 1:
                result.append(max(values))
            elif case['projection'] == 2:
                result.append(min(values))
            else:
                result.append(sum(values) / len(values))
    return result


driver = r'''
import Foundation
import Metal
import simd

func phantom(_ i: Int, _ j: Int, _ k: Int) -> Float { Float(((i * 7 + j * 3 + k * 11) % 23) * 10 + (i ^ j ^ k)) }
func ramp(_ i: Int, _ j: Int, _ k: Int) -> Float { 256 + Float(i) + 2 * Float(j) + 3 * Float(k) }
func step(_ i: Int, _ j: Int, _ k: Int) -> Float { i >= 6 ? 1000 : 0 }
func voxels(_ w: Int, _ h: Int, _ d: Int, _ f: (Int, Int, Int) -> Float) -> Data {
    var values = [Float](); values.reserveCapacity(w * h * d)
    for k in 0..<d { for j in 0..<h { for i in 0..<w { values.append(f(i, j, k)) } } }
    return values.withUnsafeBytes { Data($0) }
}
func matrix(_ m: simd_float4x4) -> [[Double]] { (0..<4).map { r in (0..<4).map { c in Double(m[c][r]) } } }
func vec(_ v: SIMD3<Float>) -> [Double] { [Double(v.x), Double(v.y), Double(v.z)] }
struct Case: Encodable {
    var name: String, volume: String, dims: [Int], voxelToWorld: [[Double]]
    var origin: [Double], rowStep: [Double], columnStep: [Double], width: Int, height: Int, background: Double
    var thickness: Double, sampleStep: Double, projection: Int
    var cubic: [Float], linear: [Float], unspecified: [Float]
}

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { exit(2) }
        let backend: MetalComputeBackend = CommandLine.arguments.contains("metal4") ? .metal4 : .metal3
        if backend == .metal4 && !Metal4ComputeSubmitter.isSupported(device) { exit(3) }
        let engine = try MPRMetalReslicer(device: device, backend: backend)
        var cases = [Case]()
        func values(_ data: Data) -> [Float] { data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) } }
        func run(_ name: String, _ volumeName: String, _ volume: ResliceVolume, origin: SIMD3<Float>, row: SIMD3<Float>,
                 column: SIMD3<Float>, width: Int, height: Int, thickness: Float = 0, step: Float = 1,
                 projection: ResliceProjection = .maximum) throws {
            func plane(_ interpolation: ResliceInterpolation?) throws -> ReslicePlane {
                if let interpolation {
                    return try ReslicePlane(origin: origin, rowStep: row, columnStep: column, width: width, height: height,
                                            thickness: thickness, sampleStep: step, projection: projection, background: -9999,
                                            interpolation: interpolation)
                }
                return try ReslicePlane(origin: origin, rowStep: row, columnStep: column, width: width, height: height,
                                        thickness: thickness, sampleStep: step, projection: projection, background: -9999)
            }
            cases.append(Case(name: name, volume: volumeName, dims: [volume.width, volume.height, volume.depth],
                              voxelToWorld: matrix(volume.voxelToWorld), origin: vec(origin), rowStep: vec(row), columnStep: vec(column),
                              width: width, height: height, background: -9999,
                              thickness: Double(thickness), sampleStep: Double(step), projection: projection.rawValue,
                              cubic: values(try engine.reslice(plane(.cubic))), linear: values(try engine.reslice(plane(.linear))),
                              unspecified: values(try engine.reslice(plane(nil)))))
        }
        let W = 16, H = 12, D = 10
        let iso = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, phantom), voxelToWorld: matrix_identity_float4x4)
        try engine.upload(iso)
        try run("centres", "phantom", iso, origin: SIMD3(0, 0, 3), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H)
        try run("half", "phantom", iso, origin: SIMD3(0.5, 0, 3.5), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H)
        let c = Float(0.5).squareRoot()
        try run("oblique", "phantom", iso, origin: SIMD3(2, 1, 1), row: SIMD3(c, 0, c) * 0.7, column: SIMD3(0, 1, 0) * 0.9, width: 14, height: 11)
        // The MPR's own thin slab, which the host draws cubic: 1 mm sampled every 0.5 mm.
        try run("thin-mip", "phantom", iso, origin: SIMD3(2, 1, 1), row: SIMD3(c, 0, c) * 0.7, column: SIMD3(0, 1, 0) * 0.9,
                width: 14, height: 11, thickness: 1, step: 0.5, projection: .maximum)
        try run("thin-mean", "phantom", iso, origin: SIMD3(0.3, 0.2, 4.4), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0),
                width: W, height: H, thickness: 1, step: 0.5, projection: .mean)
        try run("rim", "phantom", iso, origin: SIMD3(-0.5, -0.5, 0.25), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W + 1, height: H + 1)
        // Anisotropic and sheared, as a gantry tilt leaves a stack.
        let sheared = simd_float4x4(columns: (SIMD4(0.7, 0, 0, 0), SIMD4(0, 0.7, 0, 0), SIMD4(0, 0.4, 2.5, 0), SIMD4(-3, 2, 5, 1)))
        let aniso = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, phantom), voxelToWorld: sheared)
        try engine.upload(aniso)
        try run("sheared", "phantom", aniso, origin: SIMD3(-2.1, 3.3, 9.7), row: SIMD3(0.45, 0.1, 0.3), column: SIMD3(0, 0.5, 0.6), width: 15, height: 13)
        let lin = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, ramp), voxelToWorld: matrix_identity_float4x4)
        try engine.upload(lin)
        // Every sample at least one voxel inside the far edges, so all 64 neighbours are real.
        try run("ramp", "ramp", lin, origin: SIMD3(1.6, 1.2, 1.1), row: SIMD3(0.61, 0.13, 0.17), column: SIMD3(-0.05, 0.53, 0.25), width: 12, height: 8)
        let edge = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, step), voxelToWorld: matrix_identity_float4x4)
        try engine.upload(edge)
        try run("step", "step", edge, origin: SIMD3(2, 3, 4), row: SIMD3(0.25, 0, 0), column: SIMD3(0, 1, 0.1), width: 33, height: 6)
        let out = try JSONEncoder().encode(cases)
        FileHandle.standardOutput.write(out)
    }
}
'''

failures = []
ran = []
with tempfile.TemporaryDirectory(prefix='horos-mpr-cubic-') as folder:
    work = Path(folder)
    (work / 'Check.swift').write_text(driver)
    sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'MPRMetalReslicer.swift', 'MetalPerformanceTrace.swift',
               'MetalComputePipelineCache.swift', 'Metal4ComputeSubmitter.swift']
    built = subprocess.run(['xcrun', 'swiftc', '-O', '-parse-as-library', '-suppress-warnings',
                            *[str(root / 'Horos/Sources' / name) for name in sources], str(work / 'Check.swift'),
                            '-o', str(work / 'check')], capture_output=True, text=True)
    if built.returncode != 0:
        print('FAIL: the driver does not compile:\n' + built.stderr[-3000:])
        sys.exit(1)
    for backend in ('metal3', 'metal4'):
        run = subprocess.run([str(work / 'check'), backend], capture_output=True)
        if run.returncode == 2:
            print('skipped: no Metal device here')
            sys.exit(2)
        if run.returncode == 3:
            continue
        if run.returncode != 0:
            failures.append('%s: the driver failed: %s' % (backend, run.stderr.decode()[-1500:]))
            continue
        ran.append(backend)
        for case in json.loads(run.stdout):
            name = '%s/%s' % (backend, case['name'])
            got, linear, expected = case['cubic'], case['linear'], oracle(case)
            if case['unspecified'] != linear:
                failures.append('%s: a plane that names no interpolation is not linear' % name)
            finite = [e for e in expected if e != case['background']]
            span = (max(finite) - min(finite)) if finite else 1.0
            tolerance = 1e-3 if case['name'] in ('centres', 'ramp') else 1e-4 * max(span, 1.0)
            worst = max(abs(g - e) for g, e in zip(got, expected))
            if worst > tolerance:
                failures.append('%s: worst difference from the oracle %.6g > %.6g' % (name, worst, tolerance))
            if case['name'] == 'centres':
                dims = case['dims']
                stored = [phantom(x, y, 3) for y in range(dims[1]) for x in range(dims[0])]
                if max(abs(g - s) for g, s in zip(got, stored)) > 1e-3:
                    failures.append('%s: voxel centres are not returned as stored' % name)
            if case['name'] == 'ramp':
                to_voxel = invert(case['voxelToWorld'])
                o, rs, cs = case['origin'], case['rowStep'], case['columnStep']
                exact = []
                for y in range(case['height']):
                    for x in range(case['width']):
                        v = to_voxel([o[a] + x * rs[a] + y * cs[a] for a in range(3)])
                        assert all(1 <= v[a] <= case['dims'][a] - 3 for a in range(3)), 'the ramp plane leaves the interior'
                        exact.append(256.0 + v[0] + 2 * v[1] + 3 * v[2])
                if max(abs(g - e) for g, e in zip(got, exact)) > 1e-3:
                    failures.append('%s: a linear ramp is not reproduced' % name)
            if case['name'] == 'step':
                if min(got) < -1e-3 or max(got) > 1000 + 1e-3:
                    failures.append('%s: the step overshoots its range: %.4g..%.4g' % (name, min(got), max(got)))
                # Sharper: between the voxels either side of the edge, cubic is further from linear's midpoint ramp.
                edge = [(g, l) for g, l in zip(got, linear) if 0 < l < 1000]
                if not edge or sum(abs(g - 500) for g, _ in edge) <= sum(abs(l - 500) for _, l in edge):
                    failures.append('%s: the cubic edge is not sharper than the linear one' % name)

if not ran:
    failures.append('no backend ran')

# --- the host: cubic is drawn, never measured ------------------------------------
def source(name):
    return (root / 'Horos/Sources' / name).read_bytes().decode('latin1')
bridge, view, dcmpix, dcmview = source('MPRHostBridge.m'), source('MPRDCMView.m'), source('DCMPix.m'), source('DCMView.m')
copy = bridge[bridge.find('- (float *)horosMPRCopyImageWidth:'):]
linear = copy.find('into:image error:&error]')
cubic_at = copy.find('interpolation:1 into:display')
if linear < 0 or 'interpolation:' in copy[copy.rfind('resliceWithOrigin', 0, linear):linear]:
    failures.append('the plane handed to the view (its fImage) is not resliced linearly')
if cubic_at < 0 or cubic_at < linear:
    failures.append('the cubic plane is not a second reslice after the linear one')
guard = copy[copy.rfind('if (controller.horosMPRCubicDisplay', 0, cubic_at):cubic_at]
for condition in ('controller.horosMPRCubicDisplay', '!fused', 'thickness <= HorosMPRCubicDisplayMaximumSlab'):
    if condition not in guard:
        failures.append('the cubic plane is not limited by %s' % condition)
if 'thickness:thickness sampleStep:step' not in copy[cubic_at - 400:cubic_at]:
    failures.append('the cubic plane is not the same slab as the linear one')
if 'HorosMPRCubicDisplayMaximumSlab = 1.0f' not in bridge:
    failures.append('the cubic display is not limited to the MPR\'s thin slab')
if 'objc_setAssociatedObject(self, &displayPlaneKey, nil' not in copy[:linear]:
    failures.append('a reconstruction does not drop the previous display plane first')
if 'if( moveCenter == NO)\n                [self horosMPRAttachDisplayPlaneTo: pix];' not in view:
    failures.append('the view does not hand its pix the display plane, or does it while moving the centre')
# The MPR views draw through DCMView's texture path (not the planar Metal
# renderer): the display plane enters there, through computefImageForDisplay,
# and only in place of fImage and at its size.
display = dcmpix[dcmpix.find('- (float*)computefImageForDisplay'):]
display = display[:display.find('\n}\n')]
if 'if( result == fImage && display.length == (NSUInteger) width * (NSUInteger) height * sizeof( float))' not in display:
    failures.append('the display plane is not limited to standing in for fImage at its size')
if 'srcf.data = [self computefImageForDisplay];' not in dcmpix:
    failures.append('the 8-bit representation that is drawn does not use the display plane')
if dcmview.count('[self.curDCM computefImageForDisplay]') != 3:
    failures.append('the 32-bit textures and the lens do not all use the display plane')
# What is measured or exported stays linear.
if 'computedfImage = [self computefImageForMeasurement];' not in dcmpix or 'srcf.data = [dcm computefImage];' not in dcmview:
    failures.append('measurement or raw export no longer reads the linear pixels')
if 'computefImageForDisplay' in source('ROI.m') or 'computefImageForDisplay' in source('DicomDatabase.mm'):
    failures.append('a measurement or storage path reads the display plane')
if 'boolForKey:HorosMPRCubicDisplayKey' not in bridge or 'HorosMPRCubicDisplay' in source('DefaultsOsiriX.m'):
    failures.append('the cubic display is not an unregistered preference, off unless set')
for catalog in ('it-IT', 'es'):
    text = (root / 'Horos/Resources' / (catalog + '.lproj') / 'Localizable.strings').read_text(encoding='utf-8')
    if '"Cubic Interpolation for MPR Display" = "' not in text:
        failures.append(catalog + ' lacks the menu title')
for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: cubic display reslice matches the Catmull-Rom oracle on %s; voxel centres and linear ramps exact, '
      'a sharp step stays within its voxels and is sharper than linear, and linear stays the default' % ' and '.join(ran))
