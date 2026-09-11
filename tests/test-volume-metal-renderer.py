#!/usr/bin/env python3
"""Metal volume rendering against an independent oracle (#375).

The Swift engine casts rays through a voxel grid and reduces them by
maximum, minimum, mean or front-to-back compositing through a window, a CLUT
and an opacity curve. This test rebuilds every phantom in Python from the same
formula, casts the same rays with its own trilinear interpolation and
compositing, and compares. Tolerances are fixed here, before any comparison:

- projections with the camera on a volume axis: 1e-3 (float rounding);
- oblique or perspective projections: mean |Δ| ≤ 2e-3 of the value range and
  at most 1 % of the pixels beyond 3 % of it (a sample on the volume boundary
  may fall on either side in float and double, and a MIP takes that sample);
- composite colour: mean channel error ≤ 1/255 and at most 1 % of the bytes
  beyond 3/255 (8-bit rounding, the pow() of the opacity correction and the
  same boundary samples);
- A215: with the clipping range placed on slice centres, MIP/MinIP/mean along
  each volume axis equal the independent per-slice reduction of the same
  nine-slice phantom the CPU reference test uses, to 1e-3;
- the focal point lands on the image centre; a crop box (in voxel index space), a clipping range and
  the shading toggle each change exactly what they should;
- a 16384 × 16384 × 2048 volume is refused naming its dimensions, while 800²
  and 1352² matrices of 64 slices are accepted by the memory rule.
"""
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]

W, H, D = 8, 8, 6


def phantom(i, j, k):
    return float(((i * 7 + j * 3 + k * 11) % 23) * 10 + (i ^ j ^ k))


def slab_phantom(x, y, index):
    # tests/test-thick-slab-cpu-reference.py, the CPU reference volume.
    return float((x * 7 + y * 3) % 23) + float((index * index * 5) % 17) * 10.0


def trilinear(volume, dims, v):
    for axis in range(3):
        if not (-0.5 - 1e-4 <= v[axis] <= dims[axis] - 0.5 + 1e-4):
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


def normalize(v):
    n = math.sqrt(sum(c * c for c in v)); return [c / n for c in v]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def opacity_table(points):
    curve = sorted(points)
    if not curve:
        curve = [(0.0, 0.0), (256.0, 1.0)]
    if curve[0][0] > 0:
        curve.insert(0, (0.0, 0.0))
    if curve[-1][0] < 256:
        curve.append((256.0, 1.0))
    table = []
    for index in range(256):
        x = index * 256 / 255
        previous = curve[0]; value = curve[-1][1]
        for point in curve[1:]:
            if x <= point[0]:
                span = point[0] - previous[0]
                t = (x - previous[0]) / span if span > 0 else 1.0
                value = previous[1] + (point[1] - previous[1]) * t
                break
            previous = point
        table.append(min(1.0, max(0.0, value)))
    return table


def intersect(origin, direction, lo, hi):
    t_near, t_far = -math.inf, math.inf
    for a in range(3):
        if abs(direction[a]) < 1e-12:
            if origin[a] < lo[a] or origin[a] > hi[a]:
                return None
            continue
        t0 = (lo[a] - origin[a]) / direction[a]; t1 = (hi[a] - origin[a]) / direction[a]
        t_near = max(t_near, min(t0, t1)); t_far = min(t_far, max(t0, t1))
    return (t_near, t_far) if t_far >= t_near else None


def oracle(case, volume):
    dims = case['dims']; spacing = case['spacing']
    cam = case['camera']
    forward = normalize([cam['focal'][a] - cam['position'][a] for a in range(3)])
    right = normalize(cross(forward, cam['viewUp'])); up = normalize(cross(right, forward))
    width, height = case['width'], case['height']
    aspect = width / height
    half_height = cam['parallelScale'] if cam['parallel'] else math.tan(math.radians(cam['viewAngle']) / 2)
    level, window = case['level'], case['windowWidth']
    minimum = level - window / 2
    clut = case['clut']; opacity = opacity_table([tuple(p) for p in case['opacityPoints']])
    step = case['sampleStep']; mode = case['mode']
    crop = case.get('crop'); clip = case.get('clippingRange')
    shading = case['shading']
    lo = [-0.5] * 3; hi = [dims[a] - 0.5 for a in range(3)]
    extent = math.sqrt(sum((dims[a] * spacing[a]) ** 2 for a in range(3)))
    focal_distance = math.sqrt(sum((cam['focal'][a] - cam['position'][a]) ** 2 for a in range(3)))
    near, far = (clip if clip else (0.0, focal_distance + extent * 2))
    bgra = []; scalars = []
    for y in range(height):
        for x in range(width):
            nx = (x + 0.5) / width * 2 - 1; ny = -((y + 0.5) / height * 2 - 1)
            if cam['parallel']:
                origin = [cam['position'][a] + nx * half_height * aspect * right[a] + ny * half_height * up[a] for a in range(3)]
                direction = forward
            else:
                origin = list(cam['position'])
                direction = normalize([forward[a] + nx * half_height * aspect * right[a] + ny * half_height * up[a] for a in range(3)])
            vo = [origin[a] / spacing[a] for a in range(3)]; vd = [direction[a] / spacing[a] for a in range(3)]
            hit = intersect(vo, vd, lo, hi)
            if hit and crop:
                c = intersect(vo, vd, crop[0], crop[1])
                hit = (max(hit[0], c[0]), min(hit[1], c[1])) if c else None
                if hit and hit[1] < hit[0]:
                    hit = None
            along = dot(direction, forward); eye_offset = dot([origin[a] - cam['position'][a] for a in range(3)], forward)
            t_start = t_end = None
            if hit:
                t_start = max(hit[0], (near - eye_offset) / along, 0.0)
                t_end = min(hit[1], (far - eye_offset) / along)
            acc = [0.0, 0.0, 0.0, 0.0]; reduced = 0.0; counted = 0
            if hit and t_end >= t_start:
                slack = step * 1e-4
                steps = int((t_end - t_start + slack) / step) + 1
                for s in range(steps):
                    t = t_start + s * step
                    if t > t_end + slack:
                        break
                    world = [origin[a] + direction[a] * t for a in range(3)]
                    v = [world[a] / spacing[a] for a in range(3)]
                    value = trilinear(volume, dims, v)
                    if value is None:
                        continue
                    if mode == 0:
                        w = min(1.0, max(0.0, (value - minimum) / window))
                        index = int(w * 255 + 0.5)
                        alpha = opacity[index]
                        if alpha <= 0:
                            continue
                        alpha = 1 - (1 - alpha) ** step
                        colour = [clut[index][c] / 255.0 for c in range(3)]
                        if shading['enabled']:
                            def sample(dv):
                                q = trilinear(volume, dims, [v[a] + dv[a] for a in range(3)])
                                return 0.0 if q is None else q
                            g = [sample([1, 0, 0]) - sample([-1, 0, 0]), sample([0, 1, 0]) - sample([0, -1, 0]), sample([0, 0, 1]) - sample([0, 0, -1])]
                            g = [g[a] / spacing[a] for a in range(3)]
                            mag = math.sqrt(sum(c * c for c in g))
                            normal = [-c / mag for c in g] if mag > 1e-6 else [0.0, 0.0, 0.0]
                            light = [-c for c in direction]
                            lambert = max(dot(normal, light), 0.0)
                            halfway = normalize([light[a] - direction[a] for a in range(3)])
                            spec = max(dot(normal, halfway), 0.0) ** shading['specularPower'] if mag > 1e-6 else 0.0
                            colour = [c * (shading['ambient'] + shading['diffuse'] * lambert) + shading['specular'] * spec for c in colour]
                        for c in range(3):
                            acc[c] += (1 - acc[3]) * alpha * colour[c]
                        acc[3] += (1 - acc[3]) * alpha
                        if acc[3] >= 0.99:
                            break
                    else:
                        if counted == 0:
                            reduced = value
                        elif mode == 1:
                            reduced = max(reduced, value)
                        elif mode == 2:
                            reduced = min(reduced, value)
                        else:
                            reduced += value
                        counted += 1
            if mode == 0:
                rgb = [acc[c] + (1 - acc[3]) * case['background'][c] for c in range(3)]
            elif counted:
                value = reduced / counted if mode == 3 else reduced
                scalars.append(value)
                w = min(1.0, max(0.0, (value - minimum) / window)); index = int(w * 255 + 0.5)
                rgb = [clut[index][c] / 255.0 for c in range(3)]
            else:
                scalars.append(minimum)
                rgb = list(case['background'])
            rgb = [min(1.0, max(0.0, c)) for c in rgb]
            bgra.extend([int(rgb[2] * 255 + 0.5), int(rgb[1] * 255 + 0.5), int(rgb[0] * 255 + 0.5), 255])
    return bgra, scalars


driver = r'''
import Foundation
import Metal
import simd

func phantom(_ i: Int, _ j: Int, _ k: Int) -> Float { Float(((i * 7 + j * 3 + k * 11) % 23) * 10 + (i ^ j ^ k)) }
func slabPhantom(_ x: Int, _ y: Int, _ index: Int) -> Float { Float((x * 7 + y * 3) % 23) + Float((index * index * 5) % 17) * 10 }
func voxels(_ w: Int, _ h: Int, _ d: Int, _ f: (Int, Int, Int) -> Float) -> Data {
    var values = [Float](); values.reserveCapacity(w * h * d)
    for k in 0..<d { for j in 0..<h { for i in 0..<w { values.append(f(i, j, k)) } } }
    return values.withUnsafeBytes { Data($0) }
}
func vec(_ v: SIMD3<Float>) -> [Double] { [Double(v.x), Double(v.y), Double(v.z)] }
let grey: [[Int]] = (0..<256).map { [$0, $0, $0] }
let twoTone: [[Int]] = (0..<256).map { $0 < 128 ? [255, 40, 40] : [40, 90, 255] }
func clutData(_ table: [[Int]]) -> Data { Data(table.flatMap { [UInt8($0[0]), UInt8($0[1]), UInt8($0[2]), 255] }) }

struct Case: Encodable {
    var name: String, volume: String, dims: [Int], spacing: [Double]
    var camera: Cam, width: Int, height: Int, level: Double, windowWidth: Double
    var clut: [[Int]], opacityPoints: [[Double]], mode: Int, sampleStep: Double, background: [Double]
    var shading: Shade, crop: [[Double]]?, clippingRange: [Double]?
    var bgra: [Int], scalar: [Float], milliseconds: Double
    struct Cam: Encodable { var position: [Double], focal: [Double], viewUp: [Double], parallel: Bool, parallelScale: Double, viewAngle: Double }
    struct Shade: Encodable { var enabled: Bool, ambient: Double, diffuse: Double, specular: Double, specularPower: Double }
}

@main struct Check {
    static func main() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { exit(2) }
        let engine = try VolumeMetalRenderer(device: device)
        var cases = [Case]()
        var messages = [String: String]()

        func run(_ name: String, _ volumeName: String, _ volume: ResliceVolume, spacing: SIMD3<Float>,
                 position: SIMD3<Float>, focal: SIMD3<Float>, viewUp: SIMD3<Float>, parallel: Bool = true, parallelScale: Float = 5, viewAngle: Float = 30,
                 width: Int = 12, height: Int = 10, level: Float = 120, window: Float = 240, clut: [[Int]] = grey,
                 opacity: [SIMD2<Float>] = [], mode: VolumeRenderingMode = .maximum, step: Float = 1, shading: VolumeShading = VolumeShading(enabled: false),
                 crop: (SIMD3<Float>, SIMD3<Float>)? = nil, clipping: SIMD2<Float>? = nil) throws {
            let camera = try VolumeCamera(position: position, focalPoint: focal, viewUp: viewUp, parallel: parallel, parallelScale: parallelScale, viewAngle: viewAngle, clippingRange: clipping)
            let transfer = try VolumeTransferFunction(level: level, width: window, colour: clutData(clut), opacity: VolumeTransferFunction.opacityTable(points: opacity))
            let request = try VolumeRenderRequest(camera: camera, transfer: transfer, mode: mode, shading: shading, crop: crop.map { (minimum: $0.0, maximum: $0.1) }, width: width, height: height, sampleStep: step)
            let result = try engine.render(request)
            cases.append(Case(name: name, volume: volumeName, dims: [volume.width, volume.height, volume.depth], spacing: vec(spacing),
                camera: Case.Cam(position: vec(position), focal: vec(focal), viewUp: vec(viewUp), parallel: parallel, parallelScale: Double(parallelScale), viewAngle: Double(viewAngle)),
                width: width, height: height, level: Double(level), windowWidth: Double(window), clut: clut,
                opacityPoints: opacity.map { [Double($0.x), Double($0.y)] }, mode: mode.rawValue, sampleStep: Double(step), background: [0, 0, 0],
                shading: Case.Shade(enabled: shading.enabled, ambient: Double(shading.ambient), diffuse: Double(shading.diffuse), specular: Double(shading.specular), specularPower: Double(shading.specularPower)),
                crop: crop.map { [vec($0.0), vec($0.1)] }, clippingRange: clipping.map { [Double($0.x), Double($0.y)] },
                bgra: result.bgra.map { Int($0) }, scalar: result.scalar.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }, milliseconds: result.milliseconds))
        }

        let W = 8, H = 8, D = 6
        let iso = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, phantom), voxelToWorld: matrix_identity_float4x4)
        try engine.upload(iso)
        let centre = SIMD3<Float>(3.5, 3.5, 2.5)
        // Camera on the z axis, image plane through the centre, rows along -y.
        try run("mip-z", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(3.5, 3.5, -20), focal: centre, viewUp: SIMD3(0, -1, 0))
        try run("minip-z", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(3.5, 3.5, -20), focal: centre, viewUp: SIMD3(0, -1, 0), mode: .minimum)
        try run("mean-z", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(3.5, 3.5, -20), focal: centre, viewUp: SIMD3(0, -1, 0), mode: .mean)
        try run("mip-x", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(-20, 3.5, 2.5), focal: centre, viewUp: SIMD3(0, 0, 1), width: 10, height: 12)
        try run("slab-z", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(3.5, 3.5, -20), focal: centre, viewUp: SIMD3(0, -1, 0), clipping: SIMD2(22, 24))
        try run("oblique-mip", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(-9, -7, -11), focal: centre, viewUp: SIMD3(0, 0, 1), parallelScale: 6, width: 14, height: 12, step: 0.5)
        try run("perspective-mip", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(3.5, -14, -10), focal: centre, viewUp: SIMD3(0, 0, 1), parallel: false, viewAngle: 40, width: 14, height: 12, step: 0.5)
        try run("crop-mip", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(3.5, 3.5, -20), focal: centre, viewUp: SIMD3(0, -1, 0), crop: (SIMD3(-1, -1, -1), SIMD3(3.4, 9, 9)))
        try run("composite", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(3.5, 3.5, -20), focal: centre, viewUp: SIMD3(0, -1, 0), clut: twoTone,
                opacity: [SIMD2(0, 0), SIMD2(120, 0), SIMD2(160, 0.35), SIMD2(256, 0.9)], mode: .composite, step: 0.5)
        try run("composite-shaded", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(-9, -7, -11), focal: centre, viewUp: SIMD3(0, 0, 1), clut: twoTone,
                opacity: [SIMD2(0, 0), SIMD2(120, 0), SIMD2(160, 0.35), SIMD2(256, 0.9)], mode: .composite, step: 0.5,
                shading: VolumeShading(enabled: true, ambient: 0.2, diffuse: 0.7, specular: 0.25, specularPower: 10))
        try run("composite-perspective", "phantom", iso, spacing: SIMD3(1, 1, 1), position: SIMD3(3.5, -14, -10), focal: centre, viewUp: SIMD3(0, 0, 1), parallel: false, viewAngle: 40, clut: twoTone,
                opacity: [SIMD2(0, 0), SIMD2(100, 0), SIMD2(256, 0.6)], mode: .composite, step: 0.5)

        // Anisotropic spacing: the same rays in millimetres.
        let anisoTransform = simd_float4x4(diagonal: SIMD4(0.5, 1, 2, 1))
        let aniso = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, phantom), voxelToWorld: anisoTransform)
        try engine.upload(aniso)
        try run("aniso-mip-y", "phantom", aniso, spacing: SIMD3(0.5, 1, 2), position: SIMD3(1.75, -20, 5), focal: SIMD3(1.75, 3.5, 5), viewUp: SIMD3(0, 0, 1), parallelScale: 6, width: 12, height: 14, step: 0.5)
        try run("aniso-mean-oblique", "phantom", aniso, spacing: SIMD3(0.5, 1, 2), position: SIMD3(-8, -9, 20), focal: SIMD3(1.75, 3.5, 5), viewUp: SIMD3(0, 0, 1), parallelScale: 7, width: 12, height: 12, mode: .mean, step: 0.5)

        // Focal point at the image centre: one bright voxel.
        let spot = try ResliceVolume(width: W, height: H, depth: D, voxels: voxels(W, H, D, { $0 == 5 && $1 == 2 && $2 == 3 ? 1000 : 0 }), voxelToWorld: matrix_identity_float4x4)
        try engine.upload(spot)
        try run("centre", "spot", spot, spacing: SIMD3(1, 1, 1), position: SIMD3(5, 2, -20), focal: SIMD3(5, 2, 3), viewUp: SIMD3(0, -1, 0), parallelScale: 4, width: 16, height: 16, level: 500, window: 1000)

        // A215: the CPU reference phantom, clipping range on slice centres.
        let S = 16, N = 9
        let slab = try ResliceVolume(width: S, height: S, depth: N, voxels: voxels(S, S, N, slabPhantom), voxelToWorld: matrix_identity_float4x4)
        try engine.upload(slab)
        for thickness in 1...5 {
            for position in [0, 3, 8] {
                let last = min(N - 1, position + thickness - 1)
                for mode in [VolumeRenderingMode.maximum, .minimum, .mean] {
                    // Camera 10.5 mm before slice 0 along +z: near = 10.5 + position lands on that slice centre.
                    try run("a215-z-\(mode.rawValue)-t\(thickness)-p\(position)", "slab", slab, spacing: SIMD3(1, 1, 1), position: SIMD3(7.5, 7.5, -10.5), focal: SIMD3(7.5, 7.5, 4), viewUp: SIMD3(0, -1, 0),
                            parallelScale: 8, width: S, height: S, level: 100, window: 200, mode: mode, clipping: SIMD2(10.5 + Float(position), 10.5 + Float(last) + 0.001))
                }
            }
        }
        for mode in [VolumeRenderingMode.maximum, .minimum, .mean] {
            try run("a215-x-\(mode.rawValue)", "slab", slab, spacing: SIMD3(1, 1, 1), position: SIMD3(-10.5, 7.5, 4), focal: SIMD3(7.5, 7.5, 4), viewUp: SIMD3(0, 0, 1), parallelScale: 8, width: S, height: S, level: 100, window: 200, mode: mode, clipping: SIMD2(12.5, 14.501))
            try run("a215-y-\(mode.rawValue)", "slab", slab, spacing: SIMD3(1, 1, 1), position: SIMD3(7.5, -10.5, 4), focal: SIMD3(7.5, 7.5, 4), viewUp: SIMD3(0, 0, 1), parallelScale: 8, width: S, height: S, level: 100, window: 200, mode: mode, clipping: SIMD2(13.5, 16.501))
        }

        func refusal(_ body: () throws -> Void) -> String { do { try body(); return "accepted" } catch { return "\(error)" } }
        messages["memory-huge"] = refusal { _ = try engine.memoryRequirement(width: 16384, height: 16384, depth: 2048) }
        messages["memory-800"] = refusal { _ = try engine.memoryRequirement(width: 800, height: 800, depth: 64) }
        messages["memory-1352"] = refusal { _ = try engine.memoryRequirement(width: 1352, height: 1352, depth: 64) }
        messages["camera-degenerate"] = refusal { _ = try VolumeCamera(position: SIMD3(0,0,0), focalPoint: SIMD3(0,0,0), viewUp: SIMD3(0,1,0), parallel: true, parallelScale: 1, viewAngle: 30, clippingRange: nil) }
        messages["camera-up"] = refusal { _ = try VolumeCamera(position: SIMD3(0,0,-1), focalPoint: SIMD3(0,0,0), viewUp: SIMD3(0,0,1), parallel: true, parallelScale: 1, viewAngle: 30, clippingRange: nil) }
        messages["clip-empty"] = refusal { _ = try VolumeCamera(position: SIMD3(0,0,-1), focalPoint: SIMD3(0,0,0), viewUp: SIMD3(0,1,0), parallel: true, parallelScale: 1, viewAngle: 30, clippingRange: SIMD2(5, 5)) }
        messages["transfer"] = refusal { _ = try VolumeTransferFunction(level: 0, width: 0, colour: Data(count: 1024), opacity: [Float](repeating: 0, count: 256)) }
        engine.release()
        messages["releasedReady"] = engine.isReady ? "yes" : "no"
        messages["renderWithoutVolume"] = refusal {
            let camera = try VolumeCamera(position: SIMD3(0,0,-1), focalPoint: SIMD3(0,0,0), viewUp: SIMD3(0,1,0), parallel: true, parallelScale: 1, viewAngle: 30, clippingRange: nil)
            let transfer = try VolumeTransferFunction(level: 0, width: 1, colour: clutData(grey), opacity: VolumeTransferFunction.opacityTable(points: []))
            _ = try engine.render(try VolumeRenderRequest(camera: camera, transfer: transfer, mode: .maximum, shading: VolumeShading(enabled: false), crop: nil, width: 4, height: 4, sampleStep: 1))
        }
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
        sources = ['VolumeAllocation.swift', 'VolumeSession.swift', 'MPRMetalReslicer.swift', 'VolumeMetalRenderer.swift']
        command = ['xcrun', 'swiftc', '-O', '-parse-as-library', '-suppress-warnings',
                   *[str(root / 'Horos/Sources' / name) for name in sources], str(work / 'Check.swift'), '-o', str(work / 'check')]
        subprocess.run(command, check=True)
        result = subprocess.run([str(work / 'check')], capture_output=True, timeout=240)
        if result.returncode == 2:
            print('skipped: no Metal device', file=sys.stderr)
            return 2
        if result.returncode:
            sys.stderr.write(result.stderr.decode(errors='replace'))
            raise SystemExit('driver failed with %d' % result.returncode)
        payload = json.loads(result.stdout)

    volumes = {'phantom': phantom, 'slab': slab_phantom,
               'spot': lambda i, j, k: 1000.0 if (i, j, k) == (5, 2, 3) else 0.0}
    failures = []
    checked = 0
    for case in payload['cases']:
        volume = volumes[case['volume']]
        bgra, scalars = oracle(case, volume)
        name = case['name']
        got_bgra, got_scalar = case['bgra'], case['scalar']
        if case['mode'] == 0:
            diffs = [abs(a - b) for a, b in zip(bgra, got_bgra)]
            mean = sum(diffs) / len(diffs); beyond = sum(1 for d in diffs if d > 3) / len(diffs)
            if mean > 1 or beyond > 0.01:
                index = diffs.index(max(diffs))
                failures.append('%s: colour mean %.3f/255, %.2f%% of bytes beyond 3/255, worst at byte %d (expected %d, got %d)'
                                % (name, mean, beyond * 100, index, bgra[index], got_bgra[index]))
            checked += len(bgra) // 4
            continue
        assert len(scalars) == len(got_scalar) == case['width'] * case['height'], name
        span = max(1.0, max(scalars) - min(scalars))
        diffs = [abs(a - b) for a, b in zip(scalars, got_scalar)]
        axis_aligned = name.startswith(('mip-', 'minip-', 'mean-', 'slab-', 'crop-', 'aniso-mip-y', 'centre', 'a215'))
        if axis_aligned:
            worst = max(diffs)
            if worst > 1e-3:
                index = diffs.index(worst)
                failures.append('%s: worst |Δ| %.6g > 1e-3 at pixel %d (expected %.6g, got %.6g)' % (name, worst, index, scalars[index], got_scalar[index]))
        else:
            mean = sum(diffs) / len(diffs); beyond = sum(1 for d in diffs if d > 0.03 * span) / len(diffs)
            if mean > 2e-3 * span or beyond > 0.01:
                failures.append('%s: mean |Δ| %.4g, %.2f%% of pixels beyond 3%% of the range %.4g' % (name, mean, beyond * 100, span))
        checked += len(got_scalar)
        if name.startswith('a215'):
            # Independent per-slice reduction, as the CPU reference test does.
            parts = name.split('-'); axis = parts[1]; mode = int(parts[2])
            S, N = 16, 9
            if axis == 'z':
                position = int(parts[4][1:]); thickness = int(parts[3][1:])
                last = min(N - 1, position + thickness - 1)
                for y in range(S):
                    for x in range(S):
                        values = [slab_phantom(x, y, k) for k in range(position, last + 1)]
                        expected = max(values) if mode == 1 else min(values) if mode == 2 else sum(values) / len(values)
                        # viewUp is -y, so image row 0 is voxel row 0.
                        got = got_scalar[y * S + x]
                        if abs(expected - got) > 1e-3:
                            failures.append('%s: pixel (%d,%d) expected %.4f got %.4f' % (name, x, y, expected, got)); break
        if name == 'centre':
            width, height = case['width'], case['height']
            brightest = max(range(len(got_scalar)), key=lambda n: got_scalar[n])
            bx, by = brightest % width, brightest // width
            if not (width // 2 - 1 <= bx <= width // 2 and height // 2 - 1 <= by <= height // 2):
                failures.append('centre: the focal voxel landed at (%d, %d) in a %dx%d image' % (bx, by, width, height))
        if name == 'slab-z':
            # Only slices 2..4 are inside the clipping range; a MIP of them differs from the full MIP somewhere.
            full = next(c for c in payload['cases'] if c['name'] == 'mip-z')['scalar']
            if got_scalar == full:
                failures.append('slab-z: the clipping range did not restrict the projection')
        if name == 'crop-mip':
            full = next(c for c in payload['cases'] if c['name'] == 'mip-z')['scalar']
            if got_scalar == full:
                failures.append('crop-mip: the crop box did not restrict the projection')
    shaded = next(c for c in payload['cases'] if c['name'] == 'composite-shaded')['bgra']
    plain = next(c for c in payload['cases'] if c['name'] == 'composite')['bgra']
    if shaded == plain:
        failures.append('shading changed nothing')
    m = payload['messages']
    if '16384 × 16384 × 2048' not in m['memory-huge'] or 'Nothing was reduced silently' not in m['memory-huge']:
        failures.append('a huge volume was not refused naming its dimensions: %r' % m['memory-huge'][:100])
    for key in ('memory-800', 'memory-1352'):
        if m[key] != 'accepted':
            failures.append('%s should fit the memory rule on this GPU: %s' % (key, m[key][:100]))
    for key, needle in (('camera-degenerate', 'focal point'), ('camera-up', 'parallel to the viewing direction'),
                        ('clip-empty', 'clipping range is empty'), ('transfer', 'window has no width'), ('renderWithoutVolume', 'No volume')):
        if needle not in m[key]:
            failures.append('%s was not refused as expected: %r' % (key, m[key][:100]))
    if m['releasedReady'] != 'no':
        failures.append('release() left the renderer ready')
    if failures:
        raise SystemExit('\n'.join(failures))
    print('volume metal renderer: %d cases, %d pixels within tolerance; A215 slabs, centre, crop, clipping, shading and refusals hold'
          % (len(payload['cases']), checked))
    return 0


if __name__ == '__main__':
    sys.exit(main())
