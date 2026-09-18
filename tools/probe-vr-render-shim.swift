import Foundation
import Metal
import simd

// Compiled into each revision's dylib by tools/measure-object-interleaved.py, with that revision's
// VolumeMetalRenderer.swift and its companions (#621); tools/probe-vr-render.m calls these C entry points.
// A frame is the host's: VRHostBridge.mm hands the renderer bridge a new snapshot every frame (the camera as
// numbers, the CLUT as NSData, the opacity curve as points) and the view keeps the picture until the next one.
// HOROS_METAL4 (#623) makes the renderer submit on Metal 4; otherwise the bridge picks the host's backend.

private var renderer: VolumeRendererBridge?
private var shownPicture: NSData?
private var volumeCentre = SIMD3<Float>(0, 0, 0)
private var volumeRadius: Float = 0

/// A new renderer holding a synthetic `width` × `height` × `depth` volume of 0.7 × 0.7 × 1.5 mm voxels: air
/// around a cylinder of soft tissue crossed by dense rods. Returns 0, or -1 when Metal or the upload fails.
@_cdecl("horos_ab_vr_setup")
public func horosABVRSetup(_ width: Int32, _ height: Int32, _ depth: Int32) -> Int32 {
    guard width > 0, height > 0, depth > 0 else { return -1 }
    let w = Int(width), h = Int(height), d = Int(depth)
    var values = [Float](repeating: -1000, count: w * h * d)
    for k in 0..<d {
        for j in 0..<h {
            for i in 0..<w {
                let x = Float(i) / Float(w) - 0.5, y = Float(j) / Float(h) - 0.5
                guard x * x + y * y < 0.2 else { continue }
                let rod = (i / 16 + j / 16 + k / 12) % 5 == 0
                values[(k * h + j) * w + i] = rod ? 700 : 40 + Float((i * 7 + j * 13 + k * 29) % 64)
            }
        }
    }
    do {
        #if HOROS_METAL4
        guard let device = MTLCreateSystemDefaultDevice() else { return -1 }
        let created = try VolumeRendererBridge.make(device: device, backend: .metal4)
        #else
        let created = try VolumeRendererBridge.make()
        #endif
        try created.uploadVolume(values.withUnsafeBytes { Data($0) } as NSData, width: w, height: h, depth: d,
                                 spacingX: 0.7, spacingY: 0.7, spacingZ: 1.5)
        renderer = created
        volumeCentre = SIMD3(Float(w - 1) * 0.7, Float(h - 1) * 0.7, Float(d - 1) * 1.5) * 0.5
        volumeRadius = simd_length(SIMD3(Float(w) * 0.7, Float(h) * 0.7, Float(d) * 1.5)) * 0.5
        return 0
    } catch {
        return -1
    }
}

private func colours(warm: Bool) -> NSData {
    var bytes = [UInt8](repeating: 255, count: 1024)
    for index in 0..<256 {
        let value = UInt8(index)
        bytes[4 * index] = warm ? value : UInt8(index < 128 ? 40 : 230)
        bytes[4 * index + 1] = warm ? UInt8(index * 3 / 4) : UInt8(index < 128 ? 90 : 200)
        bytes[4 * index + 2] = warm ? UInt8(index / 2) : UInt8(index < 128 ? 255 : 60)
    }
    return NSData(bytes: bytes, length: bytes.count)
}

/// One frame of `scenario` at `frame`:
///   0 composite 512 × 512, the camera turning 3° a frame, one transfer function
///   1 MIP 512 × 512, the camera turning
///   2 composite 1024 × 768, the camera turning
///   3 composite 512 × 512, the camera still, the window level moving 10 a frame
///   4 composite 512 × 512, the camera still, two presets (CLUT and curve) alternating
///   5 composite 512 × 512, the camera still, one point of the opacity curve moving
/// Returns 0, or -1 when the render fails.
@_cdecl("horos_ab_vr_render")
public func horosABVRRender(_ scenario: Int32, _ frame: Int32) -> Int32 {
    guard let renderer else { return -1 }
    let turning = scenario <= 2
    let azimuth = (turning ? Float(frame) * 3 : 30) * .pi / 180
    let eye = volumeCentre + SIMD3(sin(azimuth), 0.35, -cos(azimuth)) * volumeRadius * 3
    let camera = [eye.x, eye.y, eye.z, volumeCentre.x, volumeCentre.y, volumeCentre.z, 0, 1, 0, 1, volumeRadius, 30]
        .map { NSNumber(value: $0) }
    let second = scenario == 4 && frame % 2 == 1
    var curve: [Float] = second ? [0, 0, 60, 0, 150, 0.05, 256, 0.4] : [0, 0, 90, 0, 130, 0.02, 230, 0.6, 256, 0.8]
    if scenario == 5 { curve[4] = 110 + Float(frame % 40) }
    let level = scenario == 3 ? 300 + Double(frame % 20) * 10 : 300
    let size = scenario == 2 ? (1024, 768) : (512, 512)
    do {
        shownPicture = try renderer.render(camera: camera, near: 0, far: -1, level: level, width: 1200,
                                           clut: colours(warm: !second), opacityPoints: curve.map { NSNumber(value: $0) },
                                           mode: scenario == 1 ? 1 : 0, shading: [1, 0.15, 0.9, 0.3, 15].map { NSNumber(value: $0) },
                                           crop: [], width: size.0, height: size.1, sampleStep: 0.7, scalarBackground: -1000,
                                           imageRegion: [], scalarOut: nil)
        return 0
    } catch {
        return -1
    }
}
