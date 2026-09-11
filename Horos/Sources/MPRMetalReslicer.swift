import Foundation
import Metal
import simd

/// Reslice and projections for #374, on the volume the host already decoded.
///
/// The volume is a regular voxel grid with one affine to the world (patient
/// or the host's local frame; the engine does not care which, only that the
/// plane is expressed in the same frame). A plane is sampled at pixel centres,
/// a slab is a fixed number of samples along the plane normal, centred on the
/// plane, reduced by maximum, minimum or mean. Nothing here reads DICOM,
/// Core Data or the host's views; the host hands in bytes and geometry.
///
/// Conventions, each fixed by `tests/test-mpr-metal-reslicer.py`:
/// - voxel `(i, j, k)` has its centre at index coordinates `(i, j, k)`, so a
///   plane through voxel centres reproduces the stored values exactly;
/// - a sample is inside the volume when every index coordinate lies within
///   `[-0.5, dimension - 0.5]`; neighbours are clamped to the edge (the
///   sampler's clamp-to-edge), so the half-voxel rim repeats the edge value;
/// - a pixel whose samples all fall outside receives `background`; a mean
///   divides by the samples that were inside, as the CPU slab does.
public struct ResliceVolume {
    public let width: Int, height: Int, depth: Int
    public let voxels: Data
    /// Column-major: `voxelToWorld * (i, j, k, 1)` is the centre of voxel (i, j, k).
    public let voxelToWorld: simd_float4x4

    public init(width: Int, height: Int, depth: Int, voxels: Data, voxelToWorld: simd_float4x4) throws {
        guard width > 0, height > 0, depth > 0 else { throw ResliceFailure.geometry("The volume has no extent.") }
        let count = VolumeAllocation.byteCount(width: width, height: height, slices: depth, bytesPerVoxel: 4)
        guard count == voxels.count else {
            throw ResliceFailure.geometry("The volume bytes do not match \(VolumeAllocation.describeMatrix(width: width, height: height, slices: depth)).")
        }
        let m = voxelToWorld
        let entries = [m.columns.0, m.columns.1, m.columns.2, m.columns.3].flatMap { [$0.x, $0.y, $0.z, $0.w] }
        guard entries.allSatisfy({ $0.isFinite }) else { throw ResliceFailure.geometry("The volume geometry is not finite.") }
        let linear = simd_float3x3(SIMD3(m.columns.0.x, m.columns.0.y, m.columns.0.z),
                                   SIMD3(m.columns.1.x, m.columns.1.y, m.columns.1.z),
                                   SIMD3(m.columns.2.x, m.columns.2.y, m.columns.2.z))
        guard abs(linear.determinant) > 1e-12 else { throw ResliceFailure.geometry("The volume geometry is degenerate; no plane can be resliced from it.") }
        self.width = width; self.height = height; self.depth = depth
        self.voxels = voxels; self.voxelToWorld = voxelToWorld
    }

    /// Builds the affine the way DICOM describes a stack: the first slice's
    /// position, its row and column cosines scaled by the pixel spacing, and
    /// the step between slice positions. The step is measured, not assumed:
    /// slices must be equally spaced along the plane normal, and a series
    /// acquired in decreasing position keeps its negative step instead of
    /// being silently reordered. A gap, a non-parallel slice or a step that
    /// is not constant is refused with a reason, never regularised.
    public static func stackTransform(positions: [SIMD3<Double>], rowCosines: SIMD3<Double>,
                                      columnCosines: SIMD3<Double>, pixelSpacing: SIMD2<Double>,
                                      tolerance: Double = 1e-3) throws -> simd_float4x4 {
        guard let first = positions.first else { throw ResliceFailure.geometry("The stack has no slices.") }
        guard pixelSpacing.x > 0, pixelSpacing.y > 0, pixelSpacing.x.isFinite, pixelSpacing.y.isFinite
        else { throw ResliceFailure.geometry("The pixel spacing is not a positive finite length.") }
        let row = simd_normalize(rowCosines), column = simd_normalize(columnCosines)
        guard row.x.isFinite, column.x.isFinite, abs(simd_dot(row, column)) < 1e-4
        else { throw ResliceFailure.geometry("The row and column cosines are not orthogonal unit vectors.") }
        let normal = simd_cross(row, column)
        var step = SIMD3<Double>(0, 0, 0)
        if positions.count == 1 {
            step = normal
        } else {
            let offsets = positions.map { $0 - first }
            let along = offsets.map { simd_dot($0, normal) }
            for (index, offset) in offsets.enumerated() {
                let inPlane = offset - along[index] * normal
                guard simd_length(inPlane) <= tolerance else {
                    throw ResliceFailure.geometry("Slice \(index) is displaced \(String(format: "%.3f", simd_length(inPlane))) mm within its own plane; the stack is not a regular grid.")
                }
            }
            let first = along[1]
            guard abs(first) > tolerance else { throw ResliceFailure.geometry("Slices 0 and 1 share a position; the stack has no interval.") }
            for index in 1..<along.count {
                let interval = along[index] - along[index - 1]
                guard abs(interval - first) <= tolerance else {
                    throw ResliceFailure.geometry("The interval between slices \(index - 1) and \(index) is \(String(format: "%.3f", interval)) mm, not \(String(format: "%.3f", first)) mm; gaps or irregular spacing are not resampled silently.")
                }
            }
            step = normal * first
        }
        return simd_float4x4(columns: (
            SIMD4<Float>(Float(row.x * pixelSpacing.x), Float(row.y * pixelSpacing.x), Float(row.z * pixelSpacing.x), 0),
            SIMD4<Float>(Float(column.x * pixelSpacing.y), Float(column.y * pixelSpacing.y), Float(column.z * pixelSpacing.y), 0),
            SIMD4<Float>(Float(step.x), Float(step.y), Float(step.z), 0),
            SIMD4<Float>(Float(first.x), Float(first.y), Float(first.z), 1)))
    }
}

public enum ResliceProjection: Int {
    case maximum = 1, minimum = 2, mean = 3
}

/// One plane to produce: `origin` is the centre of pixel (0, 0); pixel (x, y)
/// has its centre at `origin + x * rowStep + y * columnStep`. The slab spans
/// `thickness` along `rowStep × columnStep`, centred on the plane, sampled
/// `sampleCount` times; a thickness of zero (or one sample) is a single plane.
public struct ReslicePlane {
    public let origin: SIMD3<Float>, rowStep: SIMD3<Float>, columnStep: SIMD3<Float>
    public let width: Int, height: Int
    public let thickness: Float, sampleCount: Int
    public let projection: ResliceProjection
    public let background: Float

    public init(origin: SIMD3<Float>, rowStep: SIMD3<Float>, columnStep: SIMD3<Float>, width: Int, height: Int,
                thickness: Float, sampleStep: Float, projection: ResliceProjection, background: Float) throws {
        guard width > 0, height > 0, width <= 16384, height <= 16384 else { throw ResliceFailure.geometry("The plane has no extent.") }
        let numbers = [origin, rowStep, columnStep].flatMap { [$0.x, $0.y, $0.z] } + [thickness, sampleStep, background]
        guard numbers.allSatisfy({ $0.isFinite }), thickness >= 0, sampleStep > 0 else { throw ResliceFailure.geometry("The plane geometry is not finite.") }
        guard simd_length(rowStep) > 0, simd_length(columnStep) > 0,
              simd_length(simd_cross(rowStep, columnStep)) > 1e-9 * simd_length(rowStep) * simd_length(columnStep)
        else { throw ResliceFailure.geometry("The plane axes are collinear.") }
        self.origin = origin; self.rowStep = rowStep; self.columnStep = columnStep
        self.width = width; self.height = height; self.thickness = thickness
        // Samples are placed every `sampleStep`, both ends of the slab included.
        sampleCount = thickness > 0 ? max(2, Int((thickness / sampleStep).rounded(.up)) + 1) : 1
        guard sampleCount <= 4096 else { throw ResliceFailure.geometry("The slab asks for \(sampleCount) samples per pixel; reduce the thickness or coarsen the step.") }
        self.projection = projection; self.background = background
    }

    var normal: SIMD3<Float> { simd_normalize(simd_cross(rowStep, columnStep)) }
}

public enum ResliceFailure: Error, CustomStringConvertible {
    case geometry(String), device(String), memory(String), cancelled

    public var description: String {
        switch self {
        case .geometry(let s), .device(let s), .memory(let s): return s
        case .cancelled: return "The reslice was cancelled."
        }
    }
    var nsError: NSError {
        let code: Int
        switch self { case .geometry: code = 1; case .device: code = 2; case .memory: code = 3; case .cancelled: code = 4 }
        return NSError(domain: "HorosMPRReslice", code: code, userInfo: [NSLocalizedDescriptionKey: description])
    }
}

/// The GPU side. One instance owns one uploaded volume; a second upload
/// replaces the first and any token still outstanding on it is cancelled.
public final class MPRMetalReslicer {
    static let shader = #"""
    #include <metal_stdlib>
    using namespace metal;
    struct Params {
        float4x4 worldToVoxel;
        float4 origin;      // xyz: centre of pixel (0,0)
        float4 rowStep;     // xyz
        float4 columnStep;  // xyz
        float4 slabStep;    // xyz: displacement between consecutive samples; w: first sample offset factor
        uint4 size;         // width, height, sampleCount, projection
        float4 extent;      // volume dims (x, y, z), background
    };
    static float sampleVolume(texture3d<float, access::read> volume, float3 v, thread bool &inside) {
        float3 dims = float3(volume.get_width(), volume.get_height(), volume.get_depth());
        inside = all(v >= -0.5) && all(v <= dims - 0.5);
        if (!inside) return 0.0;
        // Weights in float from the exact index coordinates: the hardware
        // sampler quantises them, and a slab of near-equal samples must not
        // pick its maximum by sampler precision.
        float3 base = floor(v);
        float3 w = v - base;
        int3 i0 = clamp(int3(base), int3(0), int3(dims) - 1);
        int3 i1 = clamp(int3(base) + 1, int3(0), int3(dims) - 1);
        float c000 = volume.read(uint3(i0.x, i0.y, i0.z)).r, c100 = volume.read(uint3(i1.x, i0.y, i0.z)).r;
        float c010 = volume.read(uint3(i0.x, i1.y, i0.z)).r, c110 = volume.read(uint3(i1.x, i1.y, i0.z)).r;
        float c001 = volume.read(uint3(i0.x, i0.y, i1.z)).r, c101 = volume.read(uint3(i1.x, i0.y, i1.z)).r;
        float c011 = volume.read(uint3(i0.x, i1.y, i1.z)).r, c111 = volume.read(uint3(i1.x, i1.y, i1.z)).r;
        float x00 = mix(c000, c100, w.x), x10 = mix(c010, c110, w.x);
        float x01 = mix(c001, c101, w.x), x11 = mix(c011, c111, w.x);
        return mix(mix(x00, x10, w.y), mix(x01, x11, w.y), w.z);
    }
    kernel void reslice(texture3d<float, access::read> volume [[texture(0)]],
                        device float *output [[buffer(0)]],
                        constant Params &p [[buffer(1)]],
                        uint2 gid [[thread_position_in_grid]]) {
        if (gid.x >= p.size.x || gid.y >= p.size.y) return;
        float3 centre = p.origin.xyz + float(gid.x) * p.rowStep.xyz + float(gid.y) * p.columnStep.xyz;
        float3 start = centre - p.slabStep.xyz * p.slabStep.w;
        uint n = p.size.z, projection = p.size.w;
        float accumulated = 0.0; uint counted = 0;
        for (uint s = 0; s < n; ++s) {
            float3 world = start + p.slabStep.xyz * float(s);
            float4 voxel = p.worldToVoxel * float4(world, 1.0);
            bool inside;
            float value = sampleVolume(volume, voxel.xyz, inside);
            if (!inside) continue;
            if (counted == 0) accumulated = value;
            else if (projection == 1) accumulated = max(accumulated, value);
            else if (projection == 2) accumulated = min(accumulated, value);
            else accumulated += value;
            counted += 1;
        }
        float result = p.extent.w;
        if (counted > 0) result = (projection == 3) ? accumulated / float(counted) : accumulated;
        output[gid.y * p.size.x + gid.x] = result;
    }
    """#

    public let device: MTLDevice
    let queue: MTLCommandQueue
    let pipeline: MTLComputePipelineState
    private let uploads = DispatchQueue(label: "org.horosproject.mpr.reslice.upload")
    private var texture: MTLTexture?
    private var uploaded: ResliceVolume?
    private var uploadGeneration = 0
    public private(set) var volumeBytes = 0

    public init(device: MTLDevice) throws {
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw ResliceFailure.device("Metal cannot create a command queue.") }
        self.queue = queue
        let library = try device.makeLibrary(source: Self.shader, options: nil)
        guard let function = library.makeFunction(name: "reslice") else { throw ResliceFailure.device("The reslice kernel is missing.") }
        pipeline = try device.makeComputePipelineState(function: function)
    }

    /// True once a volume is on the GPU and no later upload has replaced it.
    public var isReady: Bool { texture != nil }

    /// Refuses before allocating anything: the texture would be this many
    /// bytes, and a request the device cannot hold is named, not clamped.
    public func memoryRequirement(width: Int, height: Int, depth: Int) throws -> Int {
        try Self.memoryRequirement(device: device, width: width, height: height, depth: depth)
    }

    /// Shared with the volume renderer: one rule for what fits on the GPU.
    public static func memoryRequirement(device: MTLDevice, width: Int, height: Int, depth: Int) throws -> Int {
        let bytes = VolumeAllocation.byteCount(width: width, height: height, slices: depth, bytesPerVoxel: 4)
        guard bytes > 0, bytes != Int.max, width <= 2048, height <= 2048, depth <= 2048 else {
            throw ResliceFailure.memory("Cannot reslice a \(VolumeAllocation.describeMatrix(width: width, height: height, slices: depth)) volume: it needs \(VolumeAllocation.describe(byteCount: bytes)) of GPU memory. Nothing was reduced silently.")
        }
        let budget = Int(device.recommendedMaxWorkingSetSize)
        guard budget == 0 || bytes <= budget / 2 else {
            throw ResliceFailure.memory("Cannot reslice a \(VolumeAllocation.describeMatrix(width: width, height: height, slices: depth)) volume: it needs \(VolumeAllocation.describe(byteCount: bytes)) and this GPU offers \(VolumeAllocation.describe(byteCount: budget)). Nothing was reduced silently.")
        }
        return bytes
    }

    /// Shared with the volume renderer: the r32Float 3D texture of a volume,
    /// refused with a reason before allocation when it cannot fit.
    public static func makeTexture(device: MTLDevice, volume: ResliceVolume) throws -> (MTLTexture, Int) {
        let bytes = try memoryRequirement(device: device, width: volume.width, height: volume.height, depth: volume.depth)
        let descriptor = MTLTextureDescriptor()
        descriptor.textureType = .type3D; descriptor.pixelFormat = .r32Float
        descriptor.width = volume.width; descriptor.height = volume.height; descriptor.depth = volume.depth
        descriptor.storageMode = .shared; descriptor.usage = .shaderRead
        guard let texture = device.makeTexture(descriptor: descriptor) else {
            throw ResliceFailure.memory("Metal refused a \(VolumeAllocation.describeMatrix(width: volume.width, height: volume.height, slices: volume.depth)) texture of \(VolumeAllocation.describe(byteCount: bytes)). Nothing was reduced silently.")
        }
        volume.voxels.withUnsafeBytes { raw in
            texture.replace(region: MTLRegionMake3D(0, 0, 0, volume.width, volume.height, volume.depth), mipmapLevel: 0, slice: 0,
                            withBytes: raw.baseAddress!, bytesPerRow: volume.width * 4, bytesPerImage: volume.width * volume.height * 4)
        }
        return (texture, bytes)
    }

    /// Uploads synchronously. The host's reconstruction loop is synchronous
    /// too, so this is what it calls once per volume generation.
    public func upload(_ volume: ResliceVolume) throws {
        let bytes = try memoryRequirement(width: volume.width, height: volume.height, depth: volume.depth)
        let descriptor = MTLTextureDescriptor()
        descriptor.textureType = .type3D; descriptor.pixelFormat = .r32Float
        descriptor.width = volume.width; descriptor.height = volume.height; descriptor.depth = volume.depth
        descriptor.storageMode = .shared; descriptor.usage = .shaderRead
        guard let texture = device.makeTexture(descriptor: descriptor) else {
            throw ResliceFailure.memory("Metal refused a \(VolumeAllocation.describeMatrix(width: volume.width, height: volume.height, slices: volume.depth)) texture of \(VolumeAllocation.describe(byteCount: bytes)). Nothing was reduced silently.")
        }
        let rowBytes = volume.width * 4, sliceBytes = rowBytes * volume.height
        volume.voxels.withUnsafeBytes { raw in
            texture.replace(region: MTLRegionMake3D(0, 0, 0, volume.width, volume.height, volume.depth), mipmapLevel: 0, slice: 0,
                            withBytes: raw.baseAddress!, bytesPerRow: rowBytes, bytesPerImage: sliceBytes)
        }
        self.texture = texture; uploaded = volume; volumeBytes = bytes; uploadGeneration += 1
    }

    /// Uploads off the calling thread. A token cancelled before delivery
    /// never installs its texture, a later upload supersedes an earlier one,
    /// and the completion reports which of the three happened.
    @discardableResult
    public func upload(_ volume: ResliceVolume, token: VolumeLoadToken,
                       completion: @escaping (Result<Void, Error>) -> Void) -> VolumeLoadToken {
        uploadGeneration += 1
        let generation = uploadGeneration
        uploads.async { [weak self] in
            guard let self else { return }
            if token.isCancelled { completion(.failure(ResliceFailure.cancelled)); return }
            do {
                _ = try self.memoryRequirement(width: volume.width, height: volume.height, depth: volume.depth)
            } catch { completion(.failure(error)); return }
            let descriptor = MTLTextureDescriptor()
            descriptor.textureType = .type3D; descriptor.pixelFormat = .r32Float
            descriptor.width = volume.width; descriptor.height = volume.height; descriptor.depth = volume.depth
            descriptor.storageMode = .shared; descriptor.usage = .shaderRead
            guard let texture = self.device.makeTexture(descriptor: descriptor) else {
                completion(.failure(ResliceFailure.memory("Metal refused the volume texture."))); return
            }
            volume.voxels.withUnsafeBytes { raw in
                texture.replace(region: MTLRegionMake3D(0, 0, 0, volume.width, volume.height, volume.depth), mipmapLevel: 0, slice: 0,
                                withBytes: raw.baseAddress!, bytesPerRow: volume.width * 4, bytesPerImage: volume.width * volume.height * 4)
            }
            DispatchQueue.main.async {
                // Cancelled after the work but before delivery: the texture is
                // dropped here and the caller is told; nothing was installed.
                guard !token.isCancelled, token.deliver() else { completion(.failure(ResliceFailure.cancelled)); return }
                guard generation == self.uploadGeneration else { completion(.failure(ResliceFailure.cancelled)); return }
                self.texture = texture; self.uploaded = volume
                self.volumeBytes = volume.voxels.count
                completion(.success(()))
            }
        }
        return token
    }

    /// Drops the GPU volume. Command buffers in flight keep their own
    /// references, so this is safe during a render.
    public func release() { texture = nil; uploaded = nil; volumeBytes = 0; uploadGeneration += 1 }

    struct Params {
        var worldToVoxel: simd_float4x4
        var origin: SIMD4<Float>, rowStep: SIMD4<Float>, columnStep: SIMD4<Float>, slabStep: SIMD4<Float>
        var size: SIMD4<UInt32>
        var extent: SIMD4<Float>
    }

    /// Produces `plane.width * plane.height` floats, row-major, top row first.
    /// Runs the kernel and waits: the host consumes the pixels immediately.
    public func reslice(_ plane: ReslicePlane) throws -> Data {
        guard let texture, let uploaded else { throw ResliceFailure.device("No volume is uploaded.") }
        let count = plane.width * plane.height
        guard let output = device.makeBuffer(length: count * 4, options: .storageModeShared) else {
            throw ResliceFailure.memory("Metal refused a \(VolumeAllocation.describe(byteCount: count * 4)) output plane.")
        }
        let slabDirection = plane.sampleCount > 1 ? plane.normal * (plane.thickness / Float(plane.sampleCount - 1)) : SIMD3<Float>(0, 0, 0)
        var params = Params(
            worldToVoxel: uploaded.voxelToWorld.inverse,
            origin: SIMD4(plane.origin, 0), rowStep: SIMD4(plane.rowStep, 0), columnStep: SIMD4(plane.columnStep, 0),
            slabStep: SIMD4(slabDirection, Float(plane.sampleCount - 1) * 0.5),
            size: SIMD4(UInt32(plane.width), UInt32(plane.height), UInt32(plane.sampleCount), UInt32(plane.projection.rawValue)),
            extent: SIMD4(Float(uploaded.width), Float(uploaded.height), Float(uploaded.depth), plane.background))
        guard let command = queue.makeCommandBuffer(), let encoder = command.makeComputeCommandEncoder() else {
            throw ResliceFailure.device("Metal cannot encode the reslice.")
        }
        encoder.setComputePipelineState(pipeline)
        encoder.setTexture(texture, index: 0)
        encoder.setBuffer(output, offset: 0, index: 0)
        encoder.setBytes(&params, length: MemoryLayout<Params>.stride, index: 1)
        let w = pipeline.threadExecutionWidth, h = max(1, pipeline.maxTotalThreadsPerThreadgroup / w)
        encoder.dispatchThreads(MTLSize(width: plane.width, height: plane.height, depth: 1),
                                threadsPerThreadgroup: MTLSize(width: w, height: h, depth: 1))
        encoder.endEncoding()
        command.commit(); command.waitUntilCompleted()
        guard command.status == .completed else { throw command.error ?? ResliceFailure.device("The reslice command failed.") }
        return Data(bytes: output.contents(), count: count * 4)
    }
}

/// Objective-C face for `MPRHostBridge.m`. Vectors travel as number arrays
/// because the host speaks `float[9]` orientations and `float[3]` origins.
@objc(HorosMPRReslicer)
public final class MPRReslicerBridge: NSObject {
    private let engine: MPRMetalReslicer
    @objc public private(set) var lastMilliseconds: Double = 0

    private init(engine: MPRMetalReslicer) { self.engine = engine; super.init() }

    /// `[HorosMPRReslicer makeAndReturnError:]` from Objective-C.
    @objc public static func make() throws -> MPRReslicerBridge {
        guard let device = MTLCreateSystemDefaultDevice() else { throw ResliceFailure.device("No Metal device is available.").nsError }
        do { return MPRReslicerBridge(engine: try MPRMetalReslicer(device: device)) }
        catch let failure as ResliceFailure { throw failure.nsError }
    }

    @objc public var isReady: Bool { engine.isReady }
    @objc public var volumeBytes: Int { engine.volumeBytes }
    @objc public func releaseVolume() { engine.release() }

    /// Column-major voxel-to-world matrix in millimetres, including the host's
    /// volume translation and orientation, in the same frame as its camera.
    @objc public func uploadVolume(_ voxels: NSData, width: Int, height: Int, depth: Int,
                                   voxelToWorld: [NSNumber]) throws {
        guard voxelToWorld.count == 16 else {
            throw ResliceFailure.geometry("The volume transform is incomplete.").nsError
        }
        let m = voxelToWorld.map { $0.floatValue }
        let transform = simd_float4x4(columns: (SIMD4(m[0], m[1], m[2], m[3]),
            SIMD4(m[4], m[5], m[6], m[7]), SIMD4(m[8], m[9], m[10], m[11]), SIMD4(m[12], m[13], m[14], m[15])))
        do {
            let volume = try ResliceVolume(width: width, height: height, depth: depth, voxels: voxels as Data, voxelToWorld: transform)
            try engine.upload(volume)
        } catch let failure as ResliceFailure { throw failure.nsError }
    }

    @objc public func memoryRequirementForWidth(_ width: Int, height: Int, depth: Int) throws -> NSNumber {
        do { return NSNumber(value: try engine.memoryRequirement(width: width, height: height, depth: depth)) }
        catch let failure as ResliceFailure { throw failure.nsError }
    }

    /// `orientation` holds the DCMPix nine cosines (row, column, normal) and
    /// `origin` the centre of pixel (0, 0), both in the uploaded frame.
    @objc public func reslice(origin: [NSNumber], orientation: [NSNumber], spacing: Double, width: Int, height: Int,
                              thickness: Double, sampleStep: Double, projection: Int, background: Double) throws -> NSData {
        guard origin.count == 3, orientation.count == 9, let mode = ResliceProjection(rawValue: projection) else {
            throw ResliceFailure.geometry("The plane description is incomplete.").nsError
        }
        let o = origin.map { $0.floatValue }, c = orientation.map { $0.floatValue }
        do {
            let plane = try ReslicePlane(origin: SIMD3(o[0], o[1], o[2]),
                                         rowStep: SIMD3(c[0], c[1], c[2]) * Float(spacing),
                                         columnStep: SIMD3(c[3], c[4], c[5]) * Float(spacing),
                                         width: width, height: height, thickness: Float(thickness), sampleStep: Float(sampleStep),
                                         projection: mode, background: Float(background))
            let started = DispatchTime.now().uptimeNanoseconds
            let data = try engine.reslice(plane)
            lastMilliseconds = Double(DispatchTime.now().uptimeNanoseconds - started) / 1e6
            return data as NSData
        } catch let failure as ResliceFailure { throw failure.nsError }
    }
}
