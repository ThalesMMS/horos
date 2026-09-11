#!/usr/bin/env python3
"""Metal reslice against an independent oracle (#374).

The Swift engine samples a plane through a voxel grid and reduces a slab by
maximum, minimum or mean. This test rebuilds every phantom in Python from the
same formula, reslices the same planes with its own trilinear interpolation,
and compares. Tolerances are fixed here, before any comparison:

- planes through voxel centres and the linear ramp: 1e-3 (float rounding of
  values up to ~1e3);
- any other plane: 1e-4 relative to the value range, i.e. the interpolation
  weights agree to better than a ten-thousandth of the contrast.

Also fixed: the pixel-centre convention, the clamp-to-edge rim, a reversed
stack reproducing the forward one for the same world plane, a sheared (gantry
tilt) affine, refusal of gaps and in-plane displacement, refusal of a texture
the GPU cannot hold with the dimensions named, cancellation of an upload
before delivery, and the A225 ramp resliced repeatedly through alternating
orientations without a single differing float.
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]

W, H, D = 16, 12, 10


def phantom(i, j, k):
    # Not monotonic in any index: a mean cannot pass for a maximum, and a slab
    # taken from the wrong side gives a different answer.
    return float(((i * 7 + j * 3 + k * 11) % 23) * 10 + (i ^ j ^ k))


def ramp(i, j, k):
    return 256.0 + i + 2.0 * j + 3.0 * k


def trilinear(volume, dims, v):
    for axis in range(3):
        if not (-0.5 <= v[axis] <= dims[axis] - 0.5):
            return None
    base = [math.floor(c) for c in v]
    w = [v[a] - base[a] for a in range(3)]
    def at(i, j, k):
        i = min(max(i, 0), dims[0] - 1); j = min(max(j, 0), dims[1] - 1); k = min(max(k, 0), dims[2] - 1)
        return volume(i, j, k)
    x00 = at(base[0], base[1], base[2]) * (1 - w[0]) + at(base[0] + 1, base[1], base[2]) * w[0]
    x10 = at(base[0], base[1] + 1, base[2]) * (1 - w[0]) + at(base[0] + 1, base[1] + 1, base[2]) * w[0]
    x01 = at(base[0], base[1], base[2] + 1) * (1 - w[0]) + at(base[0] + 1, base[1], base[2] + 1) * w[0]
    x11 = at(base[0], base[1] + 1, base[2] + 1) * (1 - w[0]) + at(base[0] + 1, base[1] + 1, base[2] + 1) * w[0]
    return (x00 * (1 - w[1]) + x10 * w[1]) * (1 - w[2]) + (x01 * (1 - w[1]) + x11 * w[1]) * w[2]


def invert(m):
    # m is 4x4 row-major list of lists (affine); invert the 3x3 and translation.
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
    def apply(p):
        q = [p[a] - t[a] for a in range(3)]
        return [sum(inv[r][c] * q[c] for c in range(3)) for r in range(3)]
    return apply


def oracle(volume, dims, world_to_voxel, plane):
    o, rs, cs = plane['origin'], plane['rowStep'], plane['columnStep']
    n = [rs[1] * cs[2] - rs[2] * cs[1], rs[2] * cs[0] - rs[0] * cs[2], rs[0] * cs[1] - rs[1] * cs[0]]
    length = math.sqrt(sum(c * c for c in n)); n = [c / length for c in n]
    thickness, step = plane['thickness'], plane['sampleStep']
    count = max(2, math.ceil(thickness / step - 1e-9) + 1) if thickness > 0 else 1
    slab = [n[a] * (thickness / (count - 1)) for a in range(3)] if count > 1 else [0, 0, 0]
    result = []
    for y in range(plane['height']):
        for x in range(plane['width']):
            centre = [o[a] + x * rs[a] + y * cs[a] for a in range(3)]
            values = []
            for s in range(count):
                world = [centre[a] + slab[a] * (s - (count - 1) / 2) for a in range(3)]
                value = trilinear(volume, dims, world_to_voxel(world))
                if value is not None:
                    values.append(value)
            if not values:
                result.append(plane['background'])
            elif plane['projection'] == 1:
                result.append(max(values))
            elif plane['projection'] == 2:
                result.append(min(values))
            else:
                result.append(sum(values) / len(values))
    return result


driver = r'''
import Foundation
import Metal
import simd

func phantom(_ i: Int, _ j: Int, _ k: Int) -> Float {
    Float(((i * 7 + j * 3 + k * 11) % 23) * 10 + (i ^ j ^ k))
}
func ramp(_ i: Int, _ j: Int, _ k: Int) -> Float { 256 + Float(i) + 2 * Float(j) + 3 * Float(k) }
func voxels(_ w: Int, _ h: Int, _ d: Int, _ f: (Int, Int, Int) -> Float) -> Data {
    var values = [Float](); values.reserveCapacity(w * h * d)
    for k in 0..<d { for j in 0..<h { for i in 0..<w { values.append(f(i, j, k)) } } }
    return values.withUnsafeBytes { Data($0) }
}
func matrix(_ m: simd_float4x4) -> [[Double]] {
    (0..<4).map { r in (0..<4).map { c in Double(m[c][r]) } }
}
struct Case: Encodable {
    var name: String, volume: String, dims: [Int], voxelToWorld: [[Double]]
    var origin: [Double], rowStep: [Double], columnStep: [Double], width: Int, height: Int
    var thickness: Double, sampleStep: Double, projection: Int, background: Double
    var values: [Float]
}
func vec(_ v: SIMD3<Float>) -> [Double] { [Double(v.x), Double(v.y), Double(v.z)] }

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { exit(2) }
        let engine = try MPRMetalReslicer(device: device)
        let W = 16, H = 12, D = 10
        var cases = [Case]()
        var messages = [String: String]()

        func run(_ name: String, _ volumeName: String, _ volume: ResliceVolume, origin: SIMD3<Float>, row: SIMD3<Float>, column: SIMD3<Float>,
                 width: Int, height: Int, thickness: Float = 0, step: Float = 1, projection: ResliceProjection = .maximum, background: Float = -9999) throws {
            let plane = try ReslicePlane(origin: origin, rowStep: row, columnStep: column, width: width, height: height,
                                         thickness: thickness, sampleStep: step, projection: projection, background: background)
            let data = try engine.reslice(plane)
            let values = data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
            cases.append(Case(name: name, volume: volumeName, dims: [volume.width, volume.height, volume.depth], voxelToWorld: matrix(volume.voxelToWorld),
                              origin: vec(origin), rowStep: vec(row), columnStep: vec(column), width: width, height: height,
                              thickness: Double(thickness), sampleStep: Double(step), projection: projection.rawValue, background: Double(background), values: values))
        }

        // 1. Isotropic phantom, identity affine.
        let iso = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, phantom), voxelToWorld: matrix_identity_float4x4)
        try engine.upload(iso)
        try run("centres", "phantom", iso, origin: SIMD3(0, 0, 3), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H)
        try run("half", "phantom", iso, origin: SIMD3(0.5, 0, 3.5), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H)
        try run("rim", "phantom", iso, origin: SIMD3(-0.5, -0.5, 0), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W + 1, height: H + 1)
        let c = Float(0.5).squareRoot()
        try run("oblique", "phantom", iso, origin: SIMD3(2, 1, 1), row: SIMD3(c, 0, c) * 0.7, column: SIMD3(0, 1, 0) * 0.9, width: 14, height: 11)
        try run("sagittal", "phantom", iso, origin: SIMD3(7.25, 0, 0), row: SIMD3(0, 0, 1), column: SIMD3(0, 1, 0), width: D, height: H)
        try run("mip", "phantom", iso, origin: SIMD3(0, 0, 4), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H, thickness: 4, step: 1, projection: .maximum)
        try run("minip", "phantom", iso, origin: SIMD3(0, 0, 4), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H, thickness: 4, step: 1, projection: .minimum)
        try run("mean", "phantom", iso, origin: SIMD3(0, 0, 4), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H, thickness: 4, step: 1, projection: .mean)
        try run("mean-fine", "phantom", iso, origin: SIMD3(0.3, 0.2, 4.1), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H, thickness: 3, step: 0.4, projection: .mean)
        try run("edge-mean", "phantom", iso, origin: SIMD3(0, 0, 0), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H, thickness: 6, step: 1, projection: .mean)
        try run("outside", "phantom", iso, origin: SIMD3(0, 0, 40), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: 4, height: 3, background: -1024)
        try run("oblique-slab", "phantom", iso, origin: SIMD3(3, 2, 2), row: SIMD3(c, 0, -c), column: SIMD3(0, 1, 0), width: 9, height: H, thickness: 2.5, step: 0.5, projection: .maximum)

        // 2. Anisotropic spacing through the DICOM stack description.
        let positions = (0..<D).map { SIMD3<Double>(10, 20, 30 + 2.5 * Double($0)) }
        let anisoTransform = try ResliceVolume.stackTransform(positions: positions, rowCosines: SIMD3(1, 0, 0), columnCosines: SIMD3(0, 1, 0), pixelSpacing: SIMD2(0.5, 1.0))
        let aniso = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, phantom), voxelToWorld: anisoTransform)
        try engine.upload(aniso)
        try run("aniso-axial", "phantom", aniso, origin: SIMD3(10, 20, 30 + 2.5 * 3), row: SIMD3(0.5, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H)
        try run("aniso-coronal", "phantom", aniso, origin: SIMD3(10, 24, 30), row: SIMD3(0.5, 0, 0), column: SIMD3(0, 0, 0.5), width: W, height: 40, thickness: 3, step: 0.5, projection: .mean)

        // 3. Reversed acquisition: same world plane, decreasing positions.
        let reversedTransform = try ResliceVolume.stackTransform(positions: positions.reversed(), rowCosines: SIMD3(1, 0, 0), columnCosines: SIMD3(0, 1, 0), pixelSpacing: SIMD2(0.5, 1.0))
        let reversed = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, { phantom($0, $1, D - 1 - $2) }), voxelToWorld: reversedTransform)
        try engine.upload(reversed)
        try run("reversed-axial", "reversed", reversed, origin: SIMD3(10, 20, 30 + 2.5 * 3), row: SIMD3(0.5, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H)
        try run("reversed-mip", "reversed", reversed, origin: SIMD3(10, 20, 30 + 2.5 * 4), row: SIMD3(0.5, 0, 0), column: SIMD3(0, 1, 0), width: W, height: H, thickness: 5, step: 1.25, projection: .maximum)

        // 4. Gantry tilt: slice positions advance obliquely to the normal.
        let tilted = (0..<D).map { SIMD3<Double>(0, 0.7 * Double($0), 2.0 * Double($0)) }
        var tiltTransform = simd_float4x4(diagonal: SIMD4(1, 1, 1, 1))
        tiltTransform.columns.2 = SIMD4(0, 0.7, 2.0, 0)
        let tilt = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, phantom), voxelToWorld: tiltTransform)
        try engine.upload(tilt)
        try run("tilt-axial", "phantom", tilt, origin: SIMD3(0, 0, 3), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: 20, thickness: 0)
        try run("tilt-sagittal-mean", "phantom", tilt, origin: SIMD3(5, 0.3, 0.2), row: SIMD3(0, 0, 1), column: SIMD3(0, 1, 0), width: 20, height: 20, thickness: 2, step: 0.5, projection: .mean)
        _ = tilted

        // 5. A225: the isotropic ramp, resliced repeatedly through alternating
        // orientations; every pass must equal the first to the bit.
        let rampVolume = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, ramp), voxelToWorld: matrix_identity_float4x4)
        try engine.upload(rampVolume)
        var first = [String: Data]()
        var identical = true
        for pass in 0..<40 {
            for (name, plane) in [
                ("ramp-axial", try ReslicePlane(origin: SIMD3(0.25, 0.5, 4.5), rowStep: SIMD3(1, 0, 0), columnStep: SIMD3(0, 1, 0), width: W, height: H, thickness: 0, sampleStep: 1, projection: .maximum, background: 0)),
                ("ramp-coronal", try ReslicePlane(origin: SIMD3(0.25, 5.5, 0.5), rowStep: SIMD3(1, 0, 0), columnStep: SIMD3(0, 0, 1), width: W, height: D, thickness: 0, sampleStep: 1, projection: .maximum, background: 0)),
                ("ramp-oblique", try ReslicePlane(origin: SIMD3(1, 1, 1), rowStep: SIMD3(c, 0, c) * 0.8, columnStep: SIMD3(0, 1, 0) * 0.8, width: 10, height: H, thickness: 0, sampleStep: 1, projection: .maximum, background: 0)),
                ("ramp-mean", try ReslicePlane(origin: SIMD3(0.25, 0.5, 4.5), rowStep: SIMD3(1, 0, 0), columnStep: SIMD3(0, 1, 0), width: W, height: H, thickness: 3, sampleStep: 0.5, projection: .mean, background: 0)),
            ] {
                let data = try engine.reslice(plane)
                if pass == 0 {
                    first[name] = data
                    let values = data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
                    cases.append(Case(name: name, volume: "ramp", dims: [W, H, D], voxelToWorld: matrix(matrix_identity_float4x4),
                                      origin: vec(plane.origin), rowStep: vec(plane.rowStep), columnStep: vec(plane.columnStep), width: plane.width, height: plane.height,
                                      thickness: Double(plane.thickness), sampleStep: Double(plane.thickness > 0 ? 0.5 : 1), projection: plane.projection.rawValue, background: 0, values: values))
                } else if first[name] != data { identical = false }
            }
        }
        messages["rampIdentical"] = identical ? "yes" : "no"

        // 6. Refusals.
        func refusal(_ body: () throws -> Void) -> String {
            do { try body(); return "accepted" } catch { return "\(error)" }
        }
        var gapped = positions; gapped[5].z += 2.5
        messages["gap"] = refusal { _ = try ResliceVolume.stackTransform(positions: gapped, rowCosines: SIMD3(1, 0, 0), columnCosines: SIMD3(0, 1, 0), pixelSpacing: SIMD2(0.5, 1)) }
        var shifted = positions; shifted[2].x += 0.2
        messages["inplane"] = refusal { _ = try ResliceVolume.stackTransform(positions: shifted, rowCosines: SIMD3(1, 0, 0), columnCosines: SIMD3(0, 1, 0), pixelSpacing: SIMD2(0.5, 1)) }
        messages["degenerate"] = refusal { _ = try ResliceVolume(width: 2, height: 2, depth: 2, voxels: Data(count: 32), voxelToWorld: simd_float4x4(diagonal: SIMD4(1, 1, 0, 1))) }
        messages["bytes"] = refusal { _ = try ResliceVolume(width: 2, height: 2, depth: 2, voxels: Data(count: 31), voxelToWorld: matrix_identity_float4x4) }
        messages["collinear"] = refusal { _ = try ReslicePlane(origin: SIMD3(0,0,0), rowStep: SIMD3(1,0,0), columnStep: SIMD3(2,0,0), width: 4, height: 4, thickness: 0, sampleStep: 1, projection: .maximum, background: 0) }
        messages["memory"] = refusal { _ = try engine.memoryRequirement(width: 16384, height: 16384, depth: 2048) }
        messages["nonfinite"] = refusal { _ = try ReslicePlane(origin: SIMD3(.nan,0,0), rowStep: SIMD3(1,0,0), columnStep: SIMD3(0,1,0), width: 4, height: 4, thickness: 0, sampleStep: 1, projection: .maximum, background: 0) }

        // 7. Cancellation and supersession of asynchronous uploads.
        let registry = VolumeSessionRegistry()
        let identity = VolumeIdentity(studyInstanceUID: "s", seriesInstanceUID: "r")!
        let session = registry.open(identity: identity, owner: "mpr")!
        engine.release()
        messages["releasedReady"] = engine.isReady ? "yes" : "no"
        let cancelled = registry.makeLoadToken(for: session)!
        cancelled.cancel()
        let group = DispatchGroup()
        var outcomes = [String: String]()
        group.enter()
        engine.upload(iso, token: cancelled) { result in
            outcomes["cancelled"] = (try? result.get()) == nil ? "refused:\(result)" : "installed"; group.leave()
        }
        let superseded = registry.makeLoadToken(for: session)!
        let final = registry.makeLoadToken(for: session)!
        group.enter()
        engine.upload(aniso, token: superseded) { result in
            outcomes["superseded"] = (try? result.get()) == nil ? "refused" : "installed"; group.leave()
        }
        group.enter()
        engine.upload(tilt, token: final) { result in
            outcomes["final"] = (try? result.get()) == nil ? "refused" : "installed"; group.leave()
        }
        let deadline = Date().addingTimeInterval(20)
        while group.wait(timeout: .now()) == .timedOut && Date() < deadline {
            RunLoop.main.run(until: Date().addingTimeInterval(0.01))
        }
        messages["cancelledUpload"] = outcomes["cancelled"] ?? "timeout"
        messages["supersededUpload"] = outcomes["superseded"] ?? "timeout"
        messages["finalUpload"] = outcomes["final"] ?? "timeout"
        messages["finalReady"] = engine.isReady ? "yes" : "no"
        messages["finalBytes"] = "\(engine.volumeBytes)"
        // The installed volume must be the tilted one: reslice and compare later.
        try run("after-async", "phantom", tilt, origin: SIMD3(0, 0, 3), row: SIMD3(1, 0, 0), column: SIMD3(0, 1, 0), width: W, height: 20)
        messages["cancelledDelivered"] = cancelled.hasDelivered ? "yes" : "no"

        let encoder = JSONEncoder()
        let object: [String: Any] = ["cases": try JSONSerialization.jsonObject(with: encoder.encode(cases)), "messages": messages]
        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: object))
    }
}
'''


def main():
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / 'Check.swift').write_text(driver)
        sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'MPRMetalReslicer.swift']
        command = ['xcrun', 'swiftc', '-O', '-parse-as-library', '-suppress-warnings',
                   *[str(root / 'Horos/Sources' / name) for name in sources], str(work / 'Check.swift'), '-o', str(work / 'check')]
        subprocess.run(command, check=True)
        result = subprocess.run([str(work / 'check')], capture_output=True, timeout=180)
        if result.returncode == 2:
            print('skipped: no Metal device', file=sys.stderr)
            return 2
        if result.returncode:
            sys.stderr.write(result.stderr.decode(errors='replace'))
            raise SystemExit('driver failed with %d' % result.returncode)
        payload = json.loads(result.stdout)

    volumes = {
        'phantom': phantom,
        'ramp': ramp,
        'reversed': lambda i, j, k: phantom(i, j, k),
    }
    failures = []
    checked = 0
    for case in payload['cases']:
        dims = case['dims']
        if case['volume'] == 'reversed':
            volume = lambda i, j, k, d=dims[2]: phantom(i, j, d - 1 - k)
        else:
            volume = volumes[case['volume']]
        expected = oracle(volume, dims, invert(case['voxelToWorld']), case)
        got = case['values']
        assert len(expected) == len(got) == case['width'] * case['height'], case['name']
        span = max(1.0, max(expected) - min(expected))
        exact = case['name'] in ('centres', 'rim', 'aniso-axial', 'reversed-axial', 'after-async', 'tilt-axial') or case['volume'] == 'ramp'
        tolerance = 1e-3 if exact else 1e-4 * span
        worst = max(abs(a - b) for a, b in zip(expected, got))
        if worst > tolerance:
            index = max(range(len(got)), key=lambda n: abs(expected[n] - got[n]))
            failures.append('%s: worst |Δ| %.6g > %.6g at pixel %d (expected %.6g, got %.6g)'
                            % (case['name'], worst, tolerance, index, expected[index], got[index]))
        checked += len(got)
        if case['name'] == 'outside':
            assert all(v == -1024 for v in got), 'a plane outside the volume must read the background'
        if case['name'] == 'centres':
            assert all(got[y * dims[0] + x] == phantom(x, y, 3) for y in range(dims[1]) for x in range(dims[0])), \
                'a plane through voxel centres must return the stored values bit for bit'

    # The reversed stack and the forward one describe the same world; the
    # same world plane must give the same pixels.
    by_name = {case['name']: case['values'] for case in payload['cases']}
    if max(abs(a - b) for a, b in zip(by_name['reversed-axial'], by_name['aniso-axial'])) > 1e-3:
        failures.append('a reversed acquisition changed the pixels of the same world plane')

    m = payload['messages']
    if m['rampIdentical'] != 'yes':
        failures.append('A225: repeated ramp reslices through alternating orientations differed')
    for key, needle in (('gap', 'interval between slices 4 and 5'), ('inplane', 'displaced'), ('degenerate', 'degenerate'),
                        ('bytes', 'do not match'), ('collinear', 'collinear'), ('nonfinite', 'not finite'),
                        ('memory', '16384 × 16384 × 2048')):
        if needle not in m[key]:
            failures.append('%s was not refused with the expected reason: %r' % (key, m[key][:120]))
    if 'Nothing was reduced silently' not in m['memory']:
        failures.append('the memory refusal must say nothing was reduced silently')
    if m['releasedReady'] != 'no':
        failures.append('release() left the engine ready')
    if not m['cancelledUpload'].startswith('refused'):
        failures.append('a cancelled upload was installed: %s' % m['cancelledUpload'])
    if m['supersededUpload'] != 'refused':
        failures.append('a superseded upload was installed')
    if m['finalUpload'] != 'installed' or m['finalReady'] != 'yes':
        failures.append('the last upload did not install: %s / ready %s' % (m['finalUpload'], m['finalReady']))
    if m['finalBytes'] != str(W * H * D * 4):
        failures.append('volumeBytes does not report the installed volume: %s' % m['finalBytes'])
    if m['cancelledDelivered'] != 'no':
        failures.append('a cancelled token reported delivery')

    if failures:
        raise SystemExit('\n'.join(failures))
    print('mpr metal reslice: %d cases, %d pixels within tolerance; refusals, cancellation and A225 ramp identical'
          % (len(payload['cases']), checked))
    return 0


if __name__ == '__main__':
    sys.exit(main())
