import Foundation
import Metal
import simd

// Compiled into each revision's dylib by tools/measure-object-interleaved.py, with that revision's
// MPRMetalReslicer.swift and its companions (#620); tools/probe-mpr-reslice.m calls these C entry points.
// A reconstruction does what MPRHostBridge.m does for one frame at that revision: since #620
// (HOROS_RESLICE_INTO) the engine fills the view's image; before, the plane came back as Data and the
// host copied it into the image. The image is kept until the next frame replaces it, as the view keeps
// it: an image freed unread let the optimizer drop the host's copy into it, which the view never does.
// HOROS_METAL4 (#623) makes the engine submit on Metal 4.
// HOROS_CUBIC_DISPLAY (#702) adds what the host does with the cubic display option on: a single plane is
// resliced a second time, with cubic interpolation, into a display image kept like the view's image.

private var engine: MPRMetalReslicer?
private var planes: [ReslicePlane] = []
private var shownImage: UnsafeMutableRawPointer?
private var shownDisplay: UnsafeMutableRawPointer?
private var volumeCentre = SIMD3<Float>(0, 0, 0)
private var volumeExtent: Float = 0

/// A new engine holding a synthetic `width` × `height` × `depth` volume of 0.7 × 0.7 × 1.5 mm voxels.
/// Returns 0, or -1 when Metal, the pipeline or the upload fails.
@_cdecl("horos_ab_mpr_setup")
public func horosABMPRSetup(_ width: Int32, _ height: Int32, _ depth: Int32) -> Int32 {
    guard let device = MTLCreateSystemDefaultDevice(), width > 0, height > 0, depth > 0 else { return -1 }
    let w = Int(width), h = Int(height), d = Int(depth)
    var values = [Float](repeating: 0, count: w * h * d)
    for k in 0..<d {
        for j in 0..<h {
            for i in 0..<w { values[(k * h + j) * w + i] = Float((i * 7 + j * 13 + k * 29) % 4096) - 1024 }
        }
    }
    let spacing = SIMD3<Float>(0.7, 0.7, 1.5)
    do {
        let volume = try ResliceVolume(width: w, height: h, depth: d, voxels: values.withUnsafeBytes { Data($0) },
                                       voxelToWorld: simd_float4x4(diagonal: SIMD4(spacing, 1)))
        #if HOROS_METAL4
        let created = try MPRMetalReslicer(device: device, backend: .metal4)
        #else
        let created = try MPRMetalReslicer(device: device)
        #endif
        try created.upload(volume)
        engine = created
        volumeCentre = SIMD3(Float(w - 1), Float(h - 1), Float(d - 1)) * 0.5 * spacing
        volumeExtent = max(Float(w) * spacing.x, Float(h) * spacing.y, Float(d) * spacing.z)
        return 0
    } catch {
        return -1
    }
}

/// A plane of `width` × `height` pixels through the volume's centre, turned 20° about the axial normal and
/// tilted 15°, fitted to the volume as a view zoomed to fit it is. `thickness` mm of slab, sampled every
/// 1 mm (0 for a single plane), reduced by `projection` (1 maximum, 2 minimum, 3 mean).
/// Returns the plane's index, or -1.
@_cdecl("horos_ab_mpr_plane")
public func horosABMPRPlane(_ width: Int32, _ height: Int32, _ thickness: Float, _ projection: Int32) -> Int32 {
    guard engine != nil, let mode = ResliceProjection(rawValue: Int(projection)) else { return -1 }
    let turn = Float(20 * Double.pi / 180), tilt = Float(15 * Double.pi / 180)
    let row = SIMD3<Float>(cos(turn), sin(turn), 0)
    let column = SIMD3<Float>(-sin(turn) * cos(tilt), cos(turn) * cos(tilt), sin(tilt))
    let pixel = volumeExtent / Float(max(width, height))
    let rowStep = row * pixel, columnStep = column * pixel
    let origin = volumeCentre - rowStep * Float(width - 1) * 0.5 - columnStep * Float(height - 1) * 0.5
    do {
        planes.append(try ReslicePlane(origin: origin, rowStep: rowStep, columnStep: columnStep, width: Int(width),
                                       height: Int(height), thickness: thickness, sampleStep: 1, projection: mode,
                                       background: -1024))
        return Int32(planes.count - 1)
    } catch {
        return -1
    }
}

/// One frame of the host: returns 0, or -1 when the reconstruction fails.
@_cdecl("horos_ab_mpr_reslice")
public func horosABMPRReslice(_ index: Int32) -> Int32 {
    guard let engine, planes.indices.contains(Int(index)) else { return -1 }
    let plane = planes[Int(index)]
    let bytes = plane.width * plane.height * MemoryLayout<Float>.stride
    guard let image = malloc(bytes) else { return -1 }
    defer {
        free(shownImage)
        shownImage = image
    }
    do {
        #if HOROS_RESLICE_INTO
        try engine.reslice(plane, into: UnsafeMutableRawBufferPointer(start: image, count: bytes))
        #if HOROS_CUBIC_DISPLAY
        if plane.sampleCount == 1 {
            guard let display = malloc(bytes) else { return -1 }
            free(shownDisplay)
            shownDisplay = display
            let cubic = try ReslicePlane(origin: plane.origin, rowStep: plane.rowStep, columnStep: plane.columnStep,
                                         width: plane.width, height: plane.height, thickness: 0, sampleStep: 1,
                                         projection: plane.projection, background: plane.background, interpolation: .cubic)
            try engine.reslice(cubic, into: UnsafeMutableRawBufferPointer(start: display, count: bytes))
        }
        #endif
        #else
        let data = try engine.reslice(plane)
        guard data.count == bytes else { return -1 }
        data.withUnsafeBytes { image.copyMemory(from: $0.baseAddress!, byteCount: bytes) }
        #endif
        return 0
    } catch {
        return -1
    }
}
