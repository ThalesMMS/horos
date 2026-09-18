import Foundation
import Metal
import simd

// Compiled into each revision's dylib by tools/measure-object-interleaved.py, with that revision's MPR and VR
// engines and, from #622 on, MetalComputePipelineCache.swift; tools/probe-metal-pipelines.m calls these C entry
// points. What is timed is what opening another 3D MPR or VR window costs the engine, and the frames after.

private let device = MTLCreateSystemDefaultDevice()
// HOROS_METAL4 (#623) makes every engine here submit on Metal 4.
#if HOROS_METAL4
private let backend = MetalComputeBackend.metal4
#else
private let backend = MetalComputeBackend.metal3
#endif
private var volume: ResliceVolume?
private var keptReslicer: MPRMetalReslicer?
private var keptRenderer: VolumeMetalRenderer?
private var reslicePlane: ReslicePlane?
private var renderRequest: VolumeRenderRequest?

/// The volume, the plane and the render request every case uses, and one kept engine of each kind, which
/// compiles what the process has not compiled yet. Returns 0, or -1.
@_cdecl("horos_ab_pipelines_setup")
public func horosABPipelinesSetup() -> Int32 {
    guard let device else { return -1 }
    // HOROS_AB_VOLUME=W,H,D replaces the 128 × 128 × 64 volume, to see how uploads scale.
    var (w, h, d) = (128, 128, 64)
    if let size = ProcessInfo.processInfo.environment["HOROS_AB_VOLUME"]?.split(separator: ",").compactMap({ Int($0) }), size.count == 3 {
        (w, h, d) = (size[0], size[1], size[2])
    }
    var values = [Float](repeating: -1000, count: w * h * d)
    for k in 0..<d {
        for j in 0..<h {
            for i in 0..<w where (i - w / 2) * (i - w / 2) + (j - h / 2) * (j - h / 2) < w * h * 3 / 20 {
                values[(k * h + j) * w + i] = Float((i * 7 + j * 13 + k * 29) % 512)
            }
        }
    }
    do {
        let made = try ResliceVolume(width: w, height: h, depth: d, voxels: values.withUnsafeBytes { Data($0) },
                                     voxelToWorld: simd_float4x4(diagonal: SIMD4(1, 1, 2, 1)))
        volume = made
        reslicePlane = try ReslicePlane(origin: SIMD3(0, 0, 63), rowStep: SIMD3(0.25, 0, 0), columnStep: SIMD3(0, 0.25, 0.02),
                                        width: 512, height: 512, thickness: 6, sampleStep: 1, projection: .maximum, background: -1000)
        var colour = Data(count: 1024)
        colour.withUnsafeMutableBytes { raw in for index in 0..<256 { raw[index * 4] = UInt8(index); raw[index * 4 + 3] = 255 } }
        let transfer = try VolumeTransferFunction(level: 250, width: 500, colour: colour,
                                                  opacity: VolumeTransferFunction.opacityTable(points: [SIMD2(0, 0), SIMD2(100, 0), SIMD2(256, 0.5)]))
        let camera = try VolumeCamera(position: SIMD3(64, -150, 64), focalPoint: SIMD3(64, 64, 64), viewUp: SIMD3(0, 0, 1),
                                      parallel: true, parallelScale: 90, viewAngle: 30, clippingRange: nil)
        renderRequest = try VolumeRenderRequest(camera: camera, transfer: transfer, mode: .composite, shading: VolumeShading(enabled: true),
                                                crop: nil, width: 512, height: 512, sampleStep: 1)
        let reslicer = try MPRMetalReslicer(device: device, backend: backend)
        try reslicer.upload(made)
        keptReslicer = reslicer
        let renderer = try VolumeMetalRenderer(device: device, backend: backend)
        try renderer.upload(made)
        keptRenderer = renderer
        return 0
    } catch {
        return -1
    }
}

/// Makes the device, so that a first engine's time is its own. Returns 0, or -1 without Metal.
@_cdecl("horos_ab_pipelines_device")
public func horosABPipelinesDevice() -> Int32 {
    device == nil ? -1 : 0
}

/// Another MPR engine, dropped at once.
@_cdecl("horos_ab_pipelines_mpr_engine")
public func horosABPipelinesMPREngine() -> Int32 {
    guard let device, (try? MPRMetalReslicer(device: device, backend: backend)) != nil else { return -1 }
    return 0
}

/// Another VR engine with the host's options, dropped at once.
@_cdecl("horos_ab_pipelines_vr_engine")
public func horosABPipelinesVREngine() -> Int32 {
    guard let device, (try? VolumeMetalRenderer(device: device, backend: backend)) != nil else { return -1 }
    return 0
}

/// Another MPR window: an engine, the volume uploaded, the first plane.
@_cdecl("horos_ab_pipelines_mpr_open")
public func horosABPipelinesMPROpen() -> Int32 {
    guard let device, let volume, let reslicePlane else { return -1 }
    do {
        let reslicer = try MPRMetalReslicer(device: device, backend: backend)
        try reslicer.upload(volume)
        _ = try reslicer.reslice(reslicePlane)
        return 0
    } catch {
        return -1
    }
}

/// Another VR window: an engine, the volume uploaded, the first picture.
@_cdecl("horos_ab_pipelines_vr_open")
public func horosABPipelinesVROpen() -> Int32 {
    guard let device, let volume, let renderRequest else { return -1 }
    do {
        let renderer = try VolumeMetalRenderer(device: device, backend: backend)
        try renderer.upload(volume)
        _ = try renderer.render(renderRequest)
        return 0
    } catch {
        return -1
    }
}

/// `count` MPR engines made at once on as many threads.
@_cdecl("horos_ab_pipelines_concurrent")
public func horosABPipelinesConcurrent(_ count: Int32) -> Int32 {
    guard let device, count > 0 else { return -1 }
    let lock = NSLock()
    var made = 0
    DispatchQueue.concurrentPerform(iterations: Int(count)) { _ in
        if (try? MPRMetalReslicer(device: device, backend: backend)) != nil { lock.withLock { made += 1 } }
    }
    return made == Int(count) ? 0 : -1
}

/// A plane of the kept MPR engine.
@_cdecl("horos_ab_pipelines_reslice")
public func horosABPipelinesReslice() -> Int32 {
    guard let keptReslicer, let reslicePlane, (try? keptReslicer.reslice(reslicePlane)) != nil else { return -1 }
    return 0
}

/// A picture of the kept VR engine.
@_cdecl("horos_ab_pipelines_render")
public func horosABPipelinesRender() -> Int32 {
    guard let keptRenderer, let renderRequest, (try? keptRenderer.render(renderRequest)) != nil else { return -1 }
    return 0
}
