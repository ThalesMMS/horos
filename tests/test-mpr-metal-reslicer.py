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

The output plane is reused (#620): repeated planes make one buffer; a larger
plane grows it once and a smaller one after it reuses it; a plane a caller
still holds never changes; the pixels a larger plane shares with a smaller one
at the same positions are equal to the bit; a plane written into the caller's
memory equals the one returned as Data and a destination too small is refused;
two engines alternating on two volumes never see each other's pixels; release
drops the buffer and a new upload makes one again; and reconstructions running
at once on one engine each get their own buffer and the right pixels.
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
        let backend: MetalComputeBackend = CommandLine.arguments.contains("metal4") ? .metal4 : .metal3
        if backend == .metal4 && !Metal4ComputeSubmitter.isSupported(device) { exit(3) }
        let engine = try MPRMetalReslicer(device: device, backend: backend)
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
        messages["wideTexture"] = refusal { _ = try engine.memoryRequirement(width: 2049, height: 4, depth: 4) }
        messages["tallTexture"] = refusal { _ = try engine.memoryRequirement(width: 4, height: 2049, depth: 4) }
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

        // Exercise the number-array API used by the native host, with both a
        // translated origin and a rotated, anisotropic voxel frame.
        let bridge = try MPRReslicerBridge.make()
        let affine: [NSNumber] = [0, 0.8, 0, 0, -0.8, 0, 0, 0, 0, 0, 1.5, 0, -250, -100, 60, 1]
        try bridge.uploadVolume(voxels(W, H, D, ramp) as NSData, width: W, height: H, depth: D, voxelToWorld: affine)
        let native = try bridge.reslice(origin: [-251.6, -99.2, 64.5], orientation: [0, 1, 0, -1, 0, 0, 0, 0, 1],
                                        spacing: 0.8, width: 8, height: 6, thickness: 0, sampleStep: 0.8, projection: 1, background: -9999) as Data
        let nativeValues = native.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
        messages["hostAffine"] = (0..<48).allSatisfy { abs(nativeValues[$0] - ramp(1 + $0 % 8, 2 + $0 / 8, 3)) < 1e-3 } ? "yes" : "no"
        messages["hostIncompleteAffine"] = refusal {
            try bridge.uploadVolume(voxels(W, H, D, ramp) as NSData, width: W, height: H, depth: D, voxelToWorld: [])
        }
        bridge.releaseVolume()
        messages["hostReleased"] = !bridge.isReady && bridge.volumeBytes == 0 ? "yes" : "no"

        // 8. #620: the output plane is reused without any frame seeing another's pixels.
        let reuse = try MPRMetalReslicer(device: device, backend: backend)
        try reuse.upload(rampVolume)
        let small = try ReslicePlane(origin: SIMD3(0.25, 0.5, 4.5), rowStep: SIMD3(1, 0, 0), columnStep: SIMD3(0, 1, 0),
                                     width: W, height: H, thickness: 0, sampleStep: 1, projection: .maximum, background: -1)
        // 1024 × 512 floats need 2 MiB: more than the first buffer's whole MiB.
        let large = try ReslicePlane(origin: SIMD3(0.25, 0.5, 4.5), rowStep: SIMD3(1, 0, 0), columnStep: SIMD3(0, 1, 0),
                                     width: 1024, height: 512, thickness: 0, sampleStep: 1, projection: .maximum, background: -1)
        let firstSmall = try reuse.reslice(small)
        let heldCopy = Data(firstSmall)
        var smallSame = true
        for _ in 0..<20 where try reuse.reslice(small) != firstSmall { smallSame = false }
        messages["reuseRepeatedAllocations"] = "\(reuse.outputAllocations)"
        messages["reuseRepeatedCapacity"] = "\(reuse.outputCapacity)"
        let largeData = try reuse.reslice(large)
        messages["reuseGrownAllocations"] = "\(reuse.outputAllocations)"
        messages["reuseGrownCapacity"] = "\(reuse.outputCapacity)"
        for _ in 0..<10 {
            if try reuse.reslice(small) != firstSmall { smallSame = false }
            if try reuse.reslice(large) != largeData { smallSame = false }
        }
        messages["reuseAlternatingAllocations"] = "\(reuse.outputAllocations)"
        messages["reuseSame"] = smallSame ? "yes" : "no"
        messages["reuseHeldUnchanged"] = firstSmall == heldCopy ? "yes" : "no"
        let smallValues = firstSmall.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
        let largeValues = largeData.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
        messages["reuseSharedPixels"] = (0..<H).allSatisfy { y in (0..<W).allSatisfy { x in
            largeValues[y * 1024 + x] == smallValues[y * W + x] } } ? "yes" : "no"
        messages["reuseLargeBackground"] = largeValues[511 * 1024 + 1023] == -1 ? "yes" : "no"
        var into = [Float](repeating: .nan, count: W * H)
        try into.withUnsafeMutableBytes { try reuse.reslice(small, into: $0) }
        messages["reuseInto"] = into == smallValues ? "yes" : "no"
        var short = [Float](repeating: 0, count: W * H - 1)
        messages["reuseShortDestination"] = refusal { try short.withUnsafeMutableBytes { try reuse.reslice(small, into: $0) } }

        // Two viewers: two engines, two volumes, planes interleaved.
        let other = try MPRMetalReslicer(device: device, backend: backend)
        try other.upload(iso)
        let otherFirst = try other.reslice(small)
        var separate = otherFirst != firstSmall
        for _ in 0..<10 {
            if try reuse.reslice(small) != firstSmall || other.reslice(small) != otherFirst { separate = false }
        }
        messages["reuseTwoEngines"] = separate ? "yes" : "no"

        // Release and upload again, five times.
        var cycles = true
        let beforeCycles = reuse.outputAllocations
        for _ in 0..<5 {
            reuse.release()
            if reuse.outputCapacity != 0 || reuse.isReady { cycles = false }
            if refusal({ _ = try reuse.reslice(small) }) == "accepted" { cycles = false }
            try reuse.upload(rampVolume)
            if try reuse.reslice(small) != firstSmall { cycles = false }
        }
        messages["reuseCycles"] = cycles ? "yes" : "no"
        messages["reuseCycleAllocations"] = "\(reuse.outputAllocations - beforeCycles)"

        // Reconstructions at once on one engine.
        let concurrent = try MPRMetalReslicer(device: device, backend: backend)
        try concurrent.upload(rampVolume)
        let references = [try concurrent.reslice(small), try concurrent.reslice(large)]
        let lock = NSLock()
        var concurrentSame = true
        DispatchQueue.concurrentPerform(iterations: 64) { index in
            let data = try? concurrent.reslice(index % 2 == 0 ? small : large)
            lock.withLock { if data != references[index % 2] { concurrentSame = false } }
        }
        messages["reuseConcurrent"] = concurrentSame ? "yes" : "no"
        messages["reuseConcurrentAllocations"] = "\(concurrent.outputAllocations)"
        // #623: the host's backend: HorosMetal4Compute when set, else the standard one; Metal 4 only where supported.
        if let defaults = UserDefaults(suiteName: "org.horosproject.test-mpr-metal-backend-\(ProcessInfo.processInfo.processIdentifier)") {
            let supported = Metal4ComputeSubmitter.isSupported(device)
            let unset = MetalComputeBackend.host(device: device, defaults: defaults).backend
            defaults.set(true, forKey: "HorosMetal4Compute")
            let yes = MetalComputeBackend.host(device: device, defaults: defaults).backend
            defaults.set(false, forKey: "HorosMetal4Compute")
            let no = MetalComputeBackend.host(device: device, defaults: defaults).backend
            defaults.removePersistentDomain(forName: "org.horosproject.test-mpr-metal-backend-\(ProcessInfo.processInfo.processIdentifier)")
            messages["hostBackend"] = unset == MetalComputeBackend.standard && yes == (supported ? .metal4 : .metal3) && no == .metal3 ? "yes" : "no"
        }
        // #623: engines on one device share one Metal 4 submitter, its queue and its slots.
        if backend == .metal4 {
            messages["metal4Shared"] = reuse.submitterIdentity != nil && reuse.submitterIdentity == other.submitterIdentity
                && other.submitterIdentity == concurrent.submitterIdentity ? "yes" : "no"
        }
        // #623: every Metal 4 slot comes back, and no more are kept than the submitter keeps.
        if let slots = concurrent.submissionSlots {
            messages["metal4Slots"] = slots.inFlight == 0 && slots.idle <= Metal4ComputeSubmitter.keptSlots && slots.made == slots.idle
                ? "idle" : "made \(slots.made), in flight \(slots.inFlight), idle \(slots.idle)"
        }

        let encoder = JSONEncoder()
        let object: [String: Any] = ["cases": try JSONSerialization.jsonObject(with: encoder.encode(cases)), "messages": messages]
        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: object))
    }
}
'''


def verify(payload):
    """The oracle comparisons and the messages of one backend's run: (failures, pixels checked)."""
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
    if m['hostAffine'] != 'yes' or m['hostReleased'] != 'yes':
        failures.append('the native bridge lost the affine transform or retained a released volume')
    if 'incomplete' not in m['hostIncompleteAffine']:
        failures.append('the native bridge accepted an incomplete volume transform')
    if m['rampIdentical'] != 'yes':
        failures.append('A225: repeated ramp reslices through alternating orientations differed')
    for key, needle in (('gap', 'interval between slices 4 and 5'), ('inplane', 'displaced'), ('degenerate', 'degenerate'),
                        ('bytes', 'do not match'), ('collinear', 'collinear'), ('nonfinite', 'not finite'),
                        ('memory', '16384 × 16384 × 2048'),
                        ('wideTexture', '2049 × 4 × 4'), ('tallTexture', '4 × 2049 × 4')):
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

    # #620: the kept output plane.
    if m['reuseRepeatedAllocations'] != '1' or m['reuseRepeatedCapacity'] != str(1 << 20):
        failures.append('21 planes of one size made %s output buffers, keeping %s bytes'
                        % (m['reuseRepeatedAllocations'], m['reuseRepeatedCapacity']))
    if m['reuseGrownAllocations'] != '2' or m['reuseGrownCapacity'] != str(2 << 20):
        failures.append('a larger plane made %s buffers in all, keeping %s bytes'
                        % (m['reuseGrownAllocations'], m['reuseGrownCapacity']))
    if m['reuseAlternatingAllocations'] != '2':
        failures.append('alternating sizes made more buffers: %s' % m['reuseAlternatingAllocations'])
    for key, message in (('reuseSame', 'a reused buffer changed the pixels of a repeated plane'),
                         ('reuseHeldUnchanged', 'a plane the caller held changed when the buffer was reused'),
                         ('reuseSharedPixels', 'a larger plane does not repeat the smaller plane at the same positions'),
                         ('reuseLargeBackground', 'the larger plane lost its background outside the volume'),
                         ('reuseInto', "a plane written into the caller's memory differs from the one returned as Data"),
                         ('reuseTwoEngines', 'two engines saw each other\'s pixels'),
                         ('reuseCycles', 'release kept the output buffer or a new upload gave other pixels'),
                         ('reuseConcurrent', 'reconstructions at once on one engine got the wrong pixels')):
        if m[key] != 'yes':
            failures.append(message)
    if 'destination holds' not in m['reuseShortDestination']:
        failures.append('a destination too small was not refused: %r' % m['reuseShortDestination'][:120])
    if m['reuseCycleAllocations'] != '5':
        failures.append('five release and upload cycles made %s output buffers, not one each' % m['reuseCycleAllocations'])
    if not 2 <= int(m['reuseConcurrentAllocations']) <= 64:
        failures.append('reconstructions at once made %s buffers' % m['reuseConcurrentAllocations'])

    return failures, checked


def main():
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / 'Check.swift').write_text(driver)
        sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'MPRMetalReslicer.swift', 'MetalPerformanceTrace.swift',
                   'MetalComputePipelineCache.swift', 'Metal4ComputeSubmitter.swift']
        command = ['xcrun', 'swiftc', '-O', '-parse-as-library', '-suppress-warnings',
                   *[str(root / 'Horos/Sources' / name) for name in sources], str(work / 'Check.swift'), '-o', str(work / 'check')]
        subprocess.run(command, check=True)
        payloads = {}
        for backend in ('metal3', 'metal4'):
            result = subprocess.run([str(work / 'check'), backend], capture_output=True, timeout=180)
            if result.returncode == 2:
                print('skipped: no Metal device', file=sys.stderr)
                return 2
            if result.returncode == 3 and backend == 'metal4':
                print('note: this device has no Metal 4 submission; only Metal 3 was checked', file=sys.stderr)
                continue
            if result.returncode:
                sys.stderr.write(result.stderr.decode(errors='replace'))
                raise SystemExit('%s driver failed with %d' % (backend, result.returncode))
            payloads[backend] = json.loads(result.stdout)

    failures = []
    checked = 0
    for backend, payload in payloads.items():
        found, pixels = verify(payload)
        failures += ['%s: %s' % (backend, failure) for failure in found]
        checked += pixels
    # #623: the same kernel on either submission gives the same floats.
    if payloads['metal3']['messages'].get('hostBackend') != 'yes':
        failures.append('the host backend does not follow HorosMetal4Compute, or the standard backend when it is unset')
    if 'metal4' in payloads:
        m4 = payloads['metal4']['messages']
        if m4.get('metal4Shared') != 'yes':
            failures.append('metal4: engines on one device do not share one submitter')
        if m4['metal4Slots'] != 'idle':
            failures.append('metal4: submission slots were not all given back: %s' % m4['metal4Slots'])
        for three, four in zip(payloads['metal3']['cases'], payloads['metal4']['cases']):
            if three['name'] != four['name'] or three['values'] != four['values']:
                failures.append('%s: Metal 4 resliced other floats than Metal 3' % three['name'])
    if failures:
        raise SystemExit('\n'.join(failures))
    print('mpr metal reslice (%s): %d cases each, %d pixels within tolerance; refusals, cancellation and A225 ramp identical; '
          'output plane reused%s' % (' and '.join(payloads), len(payloads['metal3']['cases']), checked,
                                     '; Metal 4 floats equal to Metal 3' if 'metal4' in payloads else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
