import Foundation
import Metal
import simd

/// Volume rendering for #375: ray casting on the same `ResliceVolume` the
/// MPR engine consumes, with the host's window, CLUT and opacity curve as the
/// transfer function, the host's camera, its clipping range as a thick slab
/// and its shading values. Composite, MIP, MinIP and mean are the four modes
/// the host's 3D viewer offers. Nothing here reads DICOM, presets, Core Data
/// or the host's views: the bridge hands in numbers.
///
/// Conventions, each fixed by `tests/test-volume-metal-renderer.py`:
/// - the image plane is centred on the focal point; pixel (x, y) has its
///   centre at `((x + 0.5) / width * 2 − 1) · halfWidth` to the right and
///   `−((y + 0.5) / height * 2 − 1) · halfHeight` up, row 0 at the top;
/// - a parallel camera has `halfHeight = parallelScale`; a perspective one
///   `halfHeight = tan(viewAngle / 2)` per unit of distance from the eye;
/// - rays march in world millimetres with a fixed `sampleStep`, starting at
///   `max(near, entry)` and stopping at `min(far, exit)` of the volume box
///   (a sample within 1e-4 of a step past the exit is still taken),
///   where near/far are the camera's clipping range measured along the
///   viewing direction from the eye; a sample counts when its index
///   coordinates lie within `[-0.5, dim − 0.5]` plus 1e-4 voxel of slack
///   (the MPR rim convention, tolerant of float-normalised directions);
/// - the transfer function is indexed by `(scalar − (level − width/2)) / width`
///   clamped to [0, 1]; opacity is per millimetre of ray and corrected for the
///   step as `1 − (1 − α)^step`; compositing is front to back, stopping at
///   α ≥ 0.99;
/// - projections output the reduced scalar and colour it through the same
///   window and CLUT, so a MIP compares numerically with the CPU slab.
public enum VolumeRenderingMode: Int {
    case composite = 0, maximum = 1, minimum = 2, mean = 3
}

public struct VolumeTransferFunction {
    public let level: Float, width: Float
    /// 256 RGBA bytes ×4.
    public let colour: Data
    /// 256 opacities in [0, 1], per millimetre of ray.
    public let opacity: [Float]

    public init(level: Float, width: Float, colour: Data, opacity: [Float]) throws {
        guard level.isFinite, width.isFinite, width > 0 else { throw ResliceFailure.geometry("The window has no width.") }
        guard colour.count == 1024, opacity.count == 256, opacity.allSatisfy({ $0.isFinite && $0 >= 0 && $0 <= 1 })
        else { throw ResliceFailure.geometry("The transfer function needs 256 colours and 256 opacities in [0, 1].") }
        self.level = level; self.width = width; self.colour = colour; self.opacity = opacity
    }

    /// The host keeps its opacity curve as points `(x, y)` with x in 0…256
    /// over the window and y in 0…1, linearly interpolated; an empty curve is
    /// the linear ramp. This expands it to the 256-entry table.
    public static func opacityTable(points: [SIMD2<Float>]) -> [Float] {
        var curve = points.filter { $0.x.isFinite && $0.y.isFinite }.sorted { $0.x < $1.x }
        if curve.isEmpty { curve = [SIMD2(0, 0), SIMD2(256, 1)] }
        if curve.first!.x > 0 { curve.insert(SIMD2(0, 0), at: 0) }
        if curve.last!.x < 256 { curve.append(SIMD2(256, 1)) }
        // Entry i is the curve at x = i · 256 / 255, so entry 0 is exactly the
        // curve's start (zero below the window, as VTK evaluates it) and entry
        // 255 its end; sampling at i + 0.5 leaks a small opacity into every
        // sample below the window, which over a long path through air adds up.
        return (0..<256).map { index -> Float in
            let x = Float(index) * 256 / 255
            var previous = curve[0]
            for point in curve.dropFirst() {
                if x <= point.x {
                    let span = point.x - previous.x
                    let t = span > 0 ? (x - previous.x) / span : 1
                    return min(1, max(0, previous.y + (point.y - previous.y) * t))
                }
                previous = point
            }
            return min(1, max(0, curve.last!.y))
        }
    }
}

public struct VolumeCamera {
    public let position: SIMD3<Float>, focalPoint: SIMD3<Float>, viewUp: SIMD3<Float>
    public let parallel: Bool
    /// Half the image height in millimetres (parallel) or the view angle in degrees (perspective).
    public let parallelScale: Float, viewAngle: Float
    /// Distances from the eye along the viewing direction; nil renders the whole box.
    public let clippingRange: SIMD2<Float>?

    public init(position: SIMD3<Float>, focalPoint: SIMD3<Float>, viewUp: SIMD3<Float>, parallel: Bool,
                parallelScale: Float, viewAngle: Float, clippingRange: SIMD2<Float>?) throws {
        let numbers = [position, focalPoint, viewUp].flatMap { [$0.x, $0.y, $0.z] } + [parallelScale, viewAngle]
        guard numbers.allSatisfy({ $0.isFinite }) else { throw ResliceFailure.geometry("The camera is not finite.") }
        guard simd_length(focalPoint - position) > 1e-6 else { throw ResliceFailure.geometry("The camera sits on its focal point.") }
        let forward = simd_normalize(focalPoint - position)
        guard simd_length(simd_cross(forward, viewUp)) > 1e-6 else { throw ResliceFailure.geometry("The view-up vector is parallel to the viewing direction.") }
        guard parallel ? parallelScale > 0 : (viewAngle > 0 && viewAngle < 180) else { throw ResliceFailure.geometry("The camera has no field of view.") }
        if let range = clippingRange {
            guard range.x.isFinite, range.y.isFinite, range.y > range.x, range.x >= 0 else { throw ResliceFailure.geometry("The clipping range is empty.") }
        }
        self.position = position; self.focalPoint = focalPoint; self.viewUp = viewUp
        self.parallel = parallel; self.parallelScale = parallelScale; self.viewAngle = viewAngle
        self.clippingRange = clippingRange
    }

    var forward: SIMD3<Float> { simd_normalize(focalPoint - position) }
    var right: SIMD3<Float> { simd_normalize(simd_cross(forward, viewUp)) }
    var up: SIMD3<Float> { simd_normalize(simd_cross(right, forward)) }
}

public struct VolumeShading {
    public let enabled: Bool
    public let ambient: Float, diffuse: Float, specular: Float, specularPower: Float
    public init(enabled: Bool, ambient: Float = 0.15, diffuse: Float = 0.9, specular: Float = 0.3, specularPower: Float = 15) {
        self.enabled = enabled; self.ambient = ambient; self.diffuse = diffuse; self.specular = specular; self.specularPower = specularPower
    }
}

public struct VolumeRenderRequest {
    public let camera: VolumeCamera
    public let transfer: VolumeTransferFunction
    public let mode: VolumeRenderingMode
    public let shading: VolumeShading
    /// Axis-aligned crop in voxel index coordinates, or nil for the whole volume.
    public let crop: (minimum: SIMD3<Float>, maximum: SIMD3<Float>)?
    public let width: Int, height: Int
    public let sampleStep: Float
    public let background: SIMD3<Float>
    /// Value written where a projection ray finds no sample; the host passes
    /// its volume minimum so the picture matches VTK's own outside value.
    public let scalarBackground: Float

    public init(camera: VolumeCamera, transfer: VolumeTransferFunction, mode: VolumeRenderingMode, shading: VolumeShading,
                crop: (minimum: SIMD3<Float>, maximum: SIMD3<Float>)?, width: Int, height: Int, sampleStep: Float,
                background: SIMD3<Float> = SIMD3(0, 0, 0), scalarBackground: Float? = nil) throws {
        guard width > 0, height > 0, width <= 8192, height <= 8192 else { throw ResliceFailure.geometry("The image has no extent.") }
        guard sampleStep.isFinite, sampleStep > 0 else { throw ResliceFailure.geometry("The sample step must be positive.") }
        if let crop { guard (0..<3).allSatisfy({ crop.maximum[$0] > crop.minimum[$0] }) else { throw ResliceFailure.geometry("The crop box is empty.") } }
        self.camera = camera; self.transfer = transfer; self.mode = mode; self.shading = shading; self.crop = crop
        self.width = width; self.height = height; self.sampleStep = sampleStep; self.background = background
        self.scalarBackground = scalarBackground ?? (transfer.level - transfer.width * 0.5)
    }
}

public struct VolumeRenderResult {
    /// width × height × 4 bytes, BGRA, row 0 at the top.
    public let bgra: Data
    /// width × height floats: for projections the reduced scalar (`background`
    /// where no sample was inside); for composite rendering the accumulated
    /// opacity of each ray, which says how much of the picture the transfer
    /// function produced.
    public let scalar: Data
    public let milliseconds: Double
}

public final class VolumeMetalRenderer {
    static let shader = #"""
    #include <metal_stdlib>
    using namespace metal;
    struct Params {
        float4x4 worldToVoxel;
        float4x4 voxelToWorld;
        float4 eye;          // xyz
        float4 forward;      // xyz
        float4 right;        // xyz, w: half width at unit distance / parallel half width
        float4 up;           // xyz, w: half height at unit distance / parallel half height
        float4 clip;         // near, far, parallel(1/0), sampleStep
        float4 window;       // level, width, mode, shadingEnabled
        float4 shading;      // ambient, diffuse, specular, specularPower
        float4 cropMin;      // xyz, w: crop enabled
        float4 cropMax;      // xyz
        float4 background;   // rgb, w: unused
        uint4 size;          // width, height, maxSteps, 0
    };
    static bool intersectBox(float3 origin, float3 direction, float3 lo, float3 hi, thread float &tNear, thread float &tFar) {
        // A direction component of zero would make (face - origin) * inf a NaN
        // on the face itself; treat that axis as a containment test instead.
        tNear = -INFINITY; tFar = INFINITY;
        for (int axis = 0; axis < 3; ++axis) {
            if (fabs(direction[axis]) < 1e-12) {
                if (origin[axis] < lo[axis] || origin[axis] > hi[axis]) return false;
                continue;
            }
            float t0 = (lo[axis] - origin[axis]) / direction[axis], t1 = (hi[axis] - origin[axis]) / direction[axis];
            tNear = max(tNear, min(t0, t1)); tFar = min(tFar, max(t0, t1));
        }
        return tFar >= tNear;
    }
    static float sampleVolume(texture3d<float, access::read> volume, float3 v, thread bool &inside) {
        // A ray direction normalised in float can overshoot a face by a few
        // 1e-7; a sample within 1e-4 voxel of the box still counts.
        float3 dims = float3(volume.get_width(), volume.get_height(), volume.get_depth());
        inside = all(v >= -0.5 - 1.0e-4) && all(v <= dims - 0.5 + 1.0e-4);
        if (!inside) return 0.0;
        float3 base = floor(v); float3 w = v - base;
        int3 i0 = clamp(int3(base), int3(0), int3(dims) - 1);
        int3 i1 = clamp(int3(base) + 1, int3(0), int3(dims) - 1);
        float c000 = volume.read(uint3(i0.x, i0.y, i0.z)).r, c100 = volume.read(uint3(i1.x, i0.y, i0.z)).r;
        float c010 = volume.read(uint3(i0.x, i1.y, i0.z)).r, c110 = volume.read(uint3(i1.x, i1.y, i0.z)).r;
        float c001 = volume.read(uint3(i0.x, i0.y, i1.z)).r, c101 = volume.read(uint3(i1.x, i0.y, i1.z)).r;
        float c011 = volume.read(uint3(i0.x, i1.y, i1.z)).r, c111 = volume.read(uint3(i1.x, i1.y, i1.z)).r;
        float x00 = mix(c000, c100, w.x), x10 = mix(c010, c110, w.x), x01 = mix(c001, c101, w.x), x11 = mix(c011, c111, w.x);
        return mix(mix(x00, x10, w.y), mix(x01, x11, w.y), w.z);
    }
    kernel void volumeRender(texture3d<float, access::read> volume [[texture(0)]],
                             texture2d<float, access::read> clut [[texture(1)]],
                             device const float *opacity [[buffer(0)]],
                             device uchar4 *output [[buffer(1)]],
                             device float *scalarOutput [[buffer(2)]],
                             constant Params &p [[buffer(3)]],
                             uint2 gid [[thread_position_in_grid]]) {
        if (gid.x >= p.size.x || gid.y >= p.size.y) return;
        float2 ndc = float2((float(gid.x) + 0.5) / float(p.size.x) * 2.0 - 1.0, -((float(gid.y) + 0.5) / float(p.size.y) * 2.0 - 1.0));
        float3 origin, direction;
        if (p.clip.z != 0.0) {
            origin = p.eye.xyz + ndc.x * p.right.w * p.right.xyz + ndc.y * p.up.w * p.up.xyz;
            direction = p.forward.xyz;
        } else {
            origin = p.eye.xyz;
            direction = normalize(p.forward.xyz + ndc.x * p.right.w * p.right.xyz + ndc.y * p.up.w * p.up.xyz);
        }
        // Box in voxel index space: [-0.5, dim - 0.5], intersected in that space.
        float3 dims = float3(volume.get_width(), volume.get_height(), volume.get_depth());
        float3 vo = (p.worldToVoxel * float4(origin, 1.0)).xyz;
        float3 vd = (p.worldToVoxel * float4(direction, 0.0)).xyz;
        float tEntry, tExit;
        bool hit = intersectBox(vo, vd, float3(-0.5), dims - 0.5, tEntry, tExit);
        if (hit && p.cropMin.w != 0.0) {
            // The crop box is axis-aligned in voxel index space, as the host's
            // cropping widget is; it need not be axis-aligned in the world.
            float cEntry, cExit;
            hit = intersectBox(vo, vd, p.cropMin.xyz, p.cropMax.xyz, cEntry, cExit);
            tEntry = max(tEntry, cEntry); tExit = min(tExit, cExit);
            hit = hit && tExit >= tEntry;
        }
        // Clipping range: distances along the viewing direction from the eye.
        float along = dot(direction, p.forward.xyz);
        float eyeOffset = dot(origin - p.eye.xyz, p.forward.xyz);
        float tNear = (p.clip.x - eyeOffset) / along, tFar = (p.clip.y - eyeOffset) / along;
        float tStart = max(max(tEntry, tNear), 0.0), tEnd = min(tExit, tFar);
        uint mode = uint(p.window.z);
        float4 acc = float4(0.0);
        float reduced = 0.0; uint counted = 0;
        float minimum = p.window.x - p.window.y * 0.5;
        if (hit && tEnd >= tStart) {
            // The last sample is included when it lies on the exit within a
            // ten-thousandth of a step, so float rounding of the exit distance
            // does not drop a boundary sample the oracle keeps.
            float step = p.clip.w;
            float slack = step * 1.0e-4;
            uint steps = min(uint((tEnd - tStart + slack) / step) + 1u, p.size.z);
            for (uint s = 0; s < steps; ++s) {
                float t = tStart + float(s) * step;
                if (t > tEnd + slack) break;
                float3 world = origin + direction * t;
                float3 v = (p.worldToVoxel * float4(world, 1.0)).xyz;
                bool inside;
                float scalar = sampleVolume(volume, v, inside);
                if (!inside) continue;
                if (mode == 0) {
                    float w = clamp((scalar - minimum) / p.window.y, 0.0, 1.0);
                    uint index = uint(w * 255.0 + 0.5);
                    float alpha = opacity[index];
                    if (alpha <= 0.0) continue;
                    alpha = 1.0 - pow(1.0 - alpha, step);
                    float3 colour = clut.read(uint2(index, 0)).rgb;
                    if (p.window.w != 0.0) {
                        bool i0, i1, i2, i3, i4, i5;
                        float gx = sampleVolume(volume, v + float3(1, 0, 0), i0) - sampleVolume(volume, v - float3(1, 0, 0), i1);
                        float gy = sampleVolume(volume, v + float3(0, 1, 0), i2) - sampleVolume(volume, v - float3(0, 1, 0), i3);
                        float gz = sampleVolume(volume, v + float3(0, 0, 1), i4) - sampleVolume(volume, v - float3(0, 0, 1), i5);
                        // Gradient in world space: covector transformed by the inverse transpose.
                        float3 gradient = (float4(gx, gy, gz, 0.0) * p.worldToVoxel).xyz;
                        float magnitude = length(gradient);
                        float3 normal = magnitude > 1e-6 ? -gradient / magnitude : float3(0.0);
                        float3 light = -direction;      // headlight, as the host's default
                        float lambert = max(dot(normal, light), 0.0);
                        float3 halfway = normalize(light - direction);
                        float spec = magnitude > 1e-6 ? pow(max(dot(normal, halfway), 0.0), p.shading.w) : 0.0;
                        colour = colour * (p.shading.x + p.shading.y * lambert) + p.shading.z * spec;
                    }
                    acc.rgb += (1.0 - acc.a) * alpha * colour;
                    acc.a += (1.0 - acc.a) * alpha;
                    if (acc.a >= 0.99) break;
                } else {
                    if (counted == 0) reduced = scalar;
                    else if (mode == 1) reduced = max(reduced, scalar);
                    else if (mode == 2) reduced = min(reduced, scalar);
                    else reduced += scalar;
                    counted += 1;
                }
            }
        }
        float3 rgb;
        if (mode == 0) {
            rgb = acc.rgb + (1.0 - acc.a) * p.background.xyz;
            scalarOutput[gid.y * p.size.x + gid.x] = acc.a;
        } else if (counted > 0) {
            float value = (mode == 3) ? reduced / float(counted) : reduced;
            scalarOutput[gid.y * p.size.x + gid.x] = value;
            float w = clamp((value - minimum) / p.window.y, 0.0, 1.0);
            rgb = clut.read(uint2(uint(w * 255.0 + 0.5), 0)).rgb;
        } else {
            scalarOutput[gid.y * p.size.x + gid.x] = p.background.w;
            rgb = p.background.xyz;
        }
        rgb = clamp(rgb, 0.0, 1.0);
        output[gid.y * p.size.x + gid.x] = uchar4(uchar(rgb.b * 255.0 + 0.5), uchar(rgb.g * 255.0 + 0.5), uchar(rgb.r * 255.0 + 0.5), 255);
    }
    """#

    public let device: MTLDevice
    let queue: MTLCommandQueue
    let pipeline: MTLComputePipelineState
    private var texture: MTLTexture?
    private var uploaded: ResliceVolume?
    public private(set) var volumeBytes = 0

    public init(device: MTLDevice) throws {
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw ResliceFailure.device("Metal cannot create a command queue.") }
        self.queue = queue
        let library = try device.makeLibrary(source: Self.shader, options: nil)
        guard let function = library.makeFunction(name: "volumeRender") else { throw ResliceFailure.device("The volume kernel is missing.") }
        pipeline = try device.makeComputePipelineState(function: function)
    }

    public var isReady: Bool { texture != nil }

    /// Same refusal as the MPR engine: named dimensions, no silent reduction.
    public func memoryRequirement(width: Int, height: Int, depth: Int) throws -> Int {
        try MPRMetalReslicer.memoryRequirement(device: device, width: width, height: height, depth: depth)
    }

    public func upload(_ volume: ResliceVolume) throws {
        let (texture, bytes) = try MPRMetalReslicer.makeTexture(device: device, volume: volume)
        self.texture = texture; uploaded = volume; volumeBytes = bytes
    }

    public func release() { texture = nil; uploaded = nil; volumeBytes = 0 }

    struct Params {
        var worldToVoxel: simd_float4x4, voxelToWorld: simd_float4x4
        var eye: SIMD4<Float>, forward: SIMD4<Float>, right: SIMD4<Float>, up: SIMD4<Float>
        var clip: SIMD4<Float>, window: SIMD4<Float>, shading: SIMD4<Float>
        var cropMin: SIMD4<Float>, cropMax: SIMD4<Float>, background: SIMD4<Float>
        var size: SIMD4<UInt32>
    }

    public func render(_ request: VolumeRenderRequest) throws -> VolumeRenderResult {
        guard let texture, let uploaded else { throw ResliceFailure.device("No volume is uploaded.") }
        let count = request.width * request.height
        guard let output = device.makeBuffer(length: count * 4, options: .storageModeShared),
              let scalar = device.makeBuffer(length: count * 4, options: .storageModeShared),
              let opacity = device.makeBuffer(bytes: request.transfer.opacity, length: 256 * 4, options: .storageModeShared)
        else { throw ResliceFailure.memory("Metal refused a \(VolumeAllocation.describe(byteCount: count * 8)) image.") }
        let tableDescriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba8Unorm, width: 256, height: 1, mipmapped: false)
        tableDescriptor.storageMode = .shared; tableDescriptor.usage = .shaderRead
        guard let clut = device.makeTexture(descriptor: tableDescriptor) else { throw ResliceFailure.device("Metal refused the colour table.") }
        request.transfer.colour.withUnsafeBytes { bytes in
            clut.replace(region: MTLRegionMake2D(0, 0, 256, 1), mipmapLevel: 0, withBytes: bytes.baseAddress!, bytesPerRow: 1024)
        }
        let camera = request.camera
        let aspect = Float(request.width) / Float(request.height)
        let halfHeight: Float = camera.parallel ? camera.parallelScale : tan(camera.viewAngle * Float.pi / 360)
        let extent = simd_length(SIMD3(Float(uploaded.width), Float(uploaded.height), Float(uploaded.depth)) *
                                 SIMD3(simd_length(uploaded.voxelToWorld.columns.0), simd_length(uploaded.voxelToWorld.columns.1), simd_length(uploaded.voxelToWorld.columns.2)))
        let range = camera.clippingRange ?? SIMD2(0, simd_length(camera.focalPoint - camera.position) + extent * 2)
        let maxSteps = UInt32(min(65536, Int(((range.y - range.x) / request.sampleStep).rounded(.up)) + 2))
        var params = Params(
            worldToVoxel: uploaded.voxelToWorld.inverse, voxelToWorld: uploaded.voxelToWorld,
            eye: SIMD4(camera.position, 0), forward: SIMD4(camera.forward, 0),
            right: SIMD4(camera.right, halfHeight * aspect), up: SIMD4(camera.up, halfHeight),
            clip: SIMD4(range.x, range.y, camera.parallel ? 1 : 0, request.sampleStep),
            window: SIMD4(request.transfer.level, request.transfer.width, Float(request.mode.rawValue), request.shading.enabled ? 1 : 0),
            shading: SIMD4(request.shading.ambient, request.shading.diffuse, request.shading.specular, request.shading.specularPower),
            cropMin: SIMD4(request.crop?.minimum ?? SIMD3(0, 0, 0), request.crop == nil ? 0 : 1),
            cropMax: SIMD4(request.crop?.maximum ?? SIMD3(0, 0, 0), 0),
            background: SIMD4(request.background, request.scalarBackground),
            size: SIMD4(UInt32(request.width), UInt32(request.height), maxSteps, 0))
        guard let command = queue.makeCommandBuffer(), let encoder = command.makeComputeCommandEncoder() else {
            throw ResliceFailure.device("Metal cannot encode the volume render.")
        }
        let started = DispatchTime.now().uptimeNanoseconds
        encoder.setComputePipelineState(pipeline)
        encoder.setTexture(texture, index: 0); encoder.setTexture(clut, index: 1)
        encoder.setBuffer(opacity, offset: 0, index: 0); encoder.setBuffer(output, offset: 0, index: 1)
        encoder.setBuffer(scalar, offset: 0, index: 2)
        encoder.setBytes(&params, length: MemoryLayout<Params>.stride, index: 3)
        let w = pipeline.threadExecutionWidth, h = max(1, pipeline.maxTotalThreadsPerThreadgroup / w)
        encoder.dispatchThreads(MTLSize(width: request.width, height: request.height, depth: 1),
                                threadsPerThreadgroup: MTLSize(width: w, height: h, depth: 1))
        encoder.endEncoding()
        command.commit(); command.waitUntilCompleted()
        guard command.status == .completed else { throw command.error ?? ResliceFailure.device("The volume render failed.") }
        let milliseconds = Double(DispatchTime.now().uptimeNanoseconds - started) / 1e6
        return VolumeRenderResult(bgra: Data(bytes: output.contents(), count: count * 4),
                                  scalar: Data(bytes: scalar.contents(), count: count * 4),
                                  milliseconds: milliseconds)
    }
}

/// Objective-C face for `VRHostBridge.mm`. Vectors travel as number arrays.
@objc(HorosVolumeRenderer)
public final class VolumeRendererBridge: NSObject {
    private let engine: VolumeMetalRenderer
    @objc public private(set) var lastMilliseconds: Double = 0

    private init(engine: VolumeMetalRenderer) { self.engine = engine; super.init() }

    /// `[HorosVolumeRenderer makeAndReturnError:]` from Objective-C.
    @objc public static func make() throws -> VolumeRendererBridge {
        guard let device = MTLCreateSystemDefaultDevice() else { throw ResliceFailure.device("No Metal device is available.").nsError }
        do { return VolumeRendererBridge(engine: try VolumeMetalRenderer(device: device)) }
        catch let failure as ResliceFailure { throw failure.nsError }
    }

    @objc public var isReady: Bool { engine.isReady }
    @objc public var volumeBytes: Int { engine.volumeBytes }
    @objc public func releaseVolume() { engine.release() }

    @objc public func uploadVolume(_ voxels: NSData, width: Int, height: Int, depth: Int,
                                   spacingX: Double, spacingY: Double, spacingZ: Double) throws {
        let transform = simd_float4x4(diagonal: SIMD4(Float(spacingX), Float(spacingY), Float(spacingZ), 1))
        let volume = try ResliceVolume(width: width, height: height, depth: depth, voxels: voxels as Data, voxelToWorld: transform)
        do { try engine.upload(volume) } catch let failure as ResliceFailure { throw failure.nsError }
    }

    /// `transform` is the voxel-to-world affine, 16 numbers row-major, as the
    /// host's 3D viewer places its volume: cosines × spacing and the DICOM origin.
    @objc public func uploadVolume(_ voxels: NSData, width: Int, height: Int, depth: Int, transform: [NSNumber]) throws {
        guard transform.count == 16 else { throw ResliceFailure.geometry("The volume transform needs 16 numbers.").nsError }
        let m = transform.map { $0.floatValue }
        let affine = simd_float4x4(rows: [SIMD4(m[0], m[1], m[2], m[3]), SIMD4(m[4], m[5], m[6], m[7]),
                                          SIMD4(m[8], m[9], m[10], m[11]), SIMD4(m[12], m[13], m[14], m[15])])
        do {
            let volume = try ResliceVolume(width: width, height: height, depth: depth, voxels: voxels as Data, voxelToWorld: affine)
            try engine.upload(volume)
        } catch let failure as ResliceFailure { throw failure.nsError }
    }

    @objc public func memoryRequirementForWidth(_ width: Int, height: Int, depth: Int) throws -> NSNumber {
        do { return NSNumber(value: try engine.memoryRequirement(width: width, height: height, depth: depth)) }
        catch let failure as ResliceFailure { throw failure.nsError }
    }

    /// Renders BGRA bytes. `camera` is position(3), focal(3), viewUp(3),
    /// parallel(1), parallelScale(1), viewAngle(1); a negative `far` means no
    /// clipping range. `opacityPoints` are the host's x/y pairs (x in 0…256).
    /// `crop` is minX, minY, minZ, maxX, maxY, maxZ in voxel index units, or empty.
    @objc public func render(camera: [NSNumber], near: Double, far: Double, level: Double, width windowWidth: Double, clut: NSData,
                             opacityPoints: [NSNumber], mode: Int, shading: [NSNumber], crop: [NSNumber], width: Int, height: Int,
                             sampleStep: Double, scalarBackground: Double, scalarOut: NSMutableData?) throws -> NSData {
        guard camera.count == 12, let renderingMode = VolumeRenderingMode(rawValue: mode) else {
            throw ResliceFailure.geometry("The render description is incomplete.").nsError
        }
        return try renderFull(camera: camera + [NSNumber(value: near), NSNumber(value: far)], level: level, windowWidth: windowWidth,
                              clut: clut, opacityPoints: opacityPoints, renderingMode: renderingMode, shading: shading, crop: crop,
                              width: width, height: height, sampleStep: sampleStep, scalarBackground: Float(scalarBackground), scalarOut: scalarOut)
    }

    private func renderFull(camera: [NSNumber], level: Double, windowWidth: Double, clut: NSData, opacityPoints: [NSNumber],
                            renderingMode: VolumeRenderingMode, shading: [NSNumber], crop: [NSNumber], width: Int, height: Int,
                            sampleStep: Double, scalarBackground: Float, scalarOut: NSMutableData?) throws -> NSData {
        let c = camera.map { $0.floatValue }
        do {
            let far = c.count > 13 ? c[13] : -1
            let volumeCamera = try VolumeCamera(position: SIMD3(c[0], c[1], c[2]), focalPoint: SIMD3(c[3], c[4], c[5]),
                                                viewUp: SIMD3(c[6], c[7], c[8]), parallel: c[9] != 0, parallelScale: c[10],
                                                viewAngle: c[11], clippingRange: far < 0 ? nil : SIMD2(max(0, c[12]), far))
            var points = [SIMD2<Float>]()
            var index = 0
            while index + 1 < opacityPoints.count {
                points.append(SIMD2(opacityPoints[index].floatValue, opacityPoints[index + 1].floatValue)); index += 2
            }
            let transfer = try VolumeTransferFunction(level: Float(level), width: Float(windowWidth), colour: clut as Data,
                                                      opacity: VolumeTransferFunction.opacityTable(points: points))
            let s = shading.map { $0.floatValue }
            let volumeShading = VolumeShading(enabled: s[0] != 0, ambient: s[1], diffuse: s[2], specular: s[3], specularPower: s[4])
            let cropBox: (minimum: SIMD3<Float>, maximum: SIMD3<Float>)? = crop.isEmpty ? nil :
                (SIMD3(crop[0].floatValue, crop[1].floatValue, crop[2].floatValue), SIMD3(crop[3].floatValue, crop[4].floatValue, crop[5].floatValue))
            let request = try VolumeRenderRequest(camera: volumeCamera, transfer: transfer, mode: renderingMode, shading: volumeShading,
                                                  crop: cropBox, width: width, height: height, sampleStep: Float(sampleStep),
                                                  scalarBackground: scalarBackground.isFinite ? scalarBackground : nil)
            let result = try engine.render(request)
            lastMilliseconds = result.milliseconds
            if let scalarOut { scalarOut.setData(result.scalar) }
            return result.bgra as NSData
        } catch let failure as ResliceFailure { throw failure.nsError }
    }
}
