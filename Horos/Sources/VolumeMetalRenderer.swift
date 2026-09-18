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
///   window and CLUT, so a MIP compares numerically with the CPU slab;
/// - a projection asked to sample as the host's VTK ray caster does (#659)
///   spans only the voxel centres, `[0, dim − 1]`, and places its samples
///   every step from the near plane, the first one past the entry: VTK starts
///   each ray on the near plane, clips it to its cropping bounds and takes
///   `1 + ⌊distance / step⌋` steps to the first sample.
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
    public let viewportSize: SIMD2<Int>, viewportOrigin: SIMD2<Int>
    public let sampleStep: Float
    public let background: SIMD3<Float>
    /// Value written where a projection ray finds no sample; the host passes
    /// its volume minimum so the picture matches VTK's own outside value.
    public let scalarBackground: Float
    /// A projection sampled as the host's VTK ray caster samples it: voxel-centre
    /// box, samples anchored on the camera's near plane (#659). Composite ignores it.
    public let anchoredProjection: Bool
    /// Up to six clipping planes in voxel index coordinates, (a, b, c, d) keeping
    /// a·v + d ≥ 0: the host's crop box, which need not be axis-aligned (#664).
    /// Each ray is clipped against them as VTK's ray caster clips it.
    public let clippingPlanes: [SIMD4<Float>]
    public static let maximumClippingPlanes = 6

    public init(camera: VolumeCamera, transfer: VolumeTransferFunction, mode: VolumeRenderingMode, shading: VolumeShading,
                crop: (minimum: SIMD3<Float>, maximum: SIMD3<Float>)?, width: Int, height: Int, sampleStep: Float,
                background: SIMD3<Float> = SIMD3(0, 0, 0), scalarBackground: Float? = nil,
                viewportSize: SIMD2<Int>? = nil, viewportOrigin: SIMD2<Int> = .zero,
                anchoredProjection: Bool = false, clippingPlanes: [SIMD4<Float>] = []) throws {
        guard width > 0, height > 0, width <= 8192, height <= 8192 else { throw ResliceFailure.geometry("The image has no extent.") }
        guard sampleStep.isFinite, sampleStep > 0 else { throw ResliceFailure.geometry("The sample step must be positive.") }
        let viewport = viewportSize ?? SIMD2(width, height)
        guard viewport.x > 0, viewport.y > 0, viewport.x <= 8192, viewport.y <= 8192,
              viewportOrigin.x >= 0, viewportOrigin.y >= 0,
              viewportOrigin.x <= viewport.x - width, viewportOrigin.y <= viewport.y - height
        else { throw ResliceFailure.geometry("The image region is outside the viewport.") }
        if let crop { guard (0..<3).allSatisfy({ crop.maximum[$0] > crop.minimum[$0] }) else { throw ResliceFailure.geometry("The crop box is empty.") } }
        guard clippingPlanes.count <= Self.maximumClippingPlanes,
              clippingPlanes.allSatisfy({ plane in (0..<4).allSatisfy { plane[$0].isFinite } && simd_length(SIMD3(plane.x, plane.y, plane.z)) > 0 })
        else { throw ResliceFailure.geometry("The crop planes are not usable.") }
        self.camera = camera; self.transfer = transfer; self.mode = mode; self.shading = shading; self.crop = crop
        self.width = width; self.height = height; self.sampleStep = sampleStep; self.background = background
        self.scalarBackground = scalarBackground ?? (transfer.level - transfer.width * 0.5)
        self.viewportSize = viewport; self.viewportOrigin = viewportOrigin
        self.anchoredProjection = anchoredProjection
        self.clippingPlanes = clippingPlanes
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
        float4 background;   // rgb, w: scalar written where a projection finds no sample
        uint4 size;          // width, height, maxSteps, anchored projection (#659)
        uint4 viewport;      // full size and top-left origin of the output region
        float4 planes[6];    // crop planes in voxel index space, a·v + d ≥ 0 kept (#664)
        uint4 clipping;      // x: how many planes
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
    static float sampleVolume(texture3d<float, access::sample> volume, float3 v, thread bool &inside, bool hardware) {
        // A ray direction normalised in float can overshoot a face by a few
        // 1e-7; a sample within 1e-4 voxel of the box still counts.
        float3 dims = float3(volume.get_width(), volume.get_height(), volume.get_depth());
        inside = all(v >= -0.5 - 1.0e-4) && all(v <= dims - 0.5 + 1.0e-4);
        if (!inside) return 0.0;
        #if VOLUME_HARDWARE_FILTERING
        constexpr sampler linearSampler(coord::normalized, address::clamp_to_edge, filter::linear);
        if (hardware) return volume.sample(linearSampler, (v + 0.5) / dims).r;
        #endif
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
    kernel void volumeBrickRanges(texture3d<float, access::read> volume [[texture(0)]],
                                  device float2 *ranges [[buffer(0)]], uint3 brick [[threadgroup_position_in_grid]],
                                  uint lane [[thread_index_in_threadgroup]]) {
        threadgroup float2 partial[128];
        int3 dims = int3(volume.get_width(), volume.get_height(), volume.get_depth());
        float2 range = float2(INFINITY, -INFINITY);
        // One-voxel halo bounds every trilinear sample within the 8-voxel brick.
        for (uint n = lane; n < 1000; n += 128) {
            int3 offset = int3(n % 10, (n / 10) % 10, n / 100) - 1;
            int3 index = clamp(int3(brick) * 8 + offset, int3(0), dims - 1);
            float value = volume.read(uint3(index)).r;
            range = float2(min(range.x, value), max(range.y, value));
        }
        partial[lane] = range;
        threadgroup_barrier(mem_flags::mem_threadgroup);
        for (uint stride = 64; stride > 0; stride >>= 1) {
            if (lane < stride) partial[lane] = float2(min(partial[lane].x, partial[lane + stride].x), max(partial[lane].y, partial[lane + stride].y));
            threadgroup_barrier(mem_flags::mem_threadgroup);
        }
        uint3 grid = (uint3(dims) + 7) / 8;
        if (lane == 0) ranges[(brick.z * grid.y + brick.y) * grid.x + brick.x] = partial[0];
    }
    kernel void volumeRender(texture3d<float, access::sample> volume [[texture(0)]],
                             texture2d<float, access::read> clut [[texture(1)]],
                             device const float *opacity [[buffer(0)]],
                             device uchar4 *output [[buffer(1)]],
                             device float *scalarOutput [[buffer(2)]],
                             constant Params &p [[buffer(3)]],
                             device const float2 *brickRanges [[buffer(4)]],
                             constant uint *opacityPrefix [[buffer(5)]],
                             uint2 gid [[thread_position_in_grid]]) {
        if (gid.x >= p.size.x || gid.y >= p.size.y) return;
        float2 pixel = float2(gid) + float2(p.viewport.zw) + 0.5;
        float2 ndc = float2(pixel.x / float(p.viewport.x) * 2.0 - 1.0, -(pixel.y / float(p.viewport.y) * 2.0 - 1.0));
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
        uint mode = uint(p.window.z);
        // VTK's fixed-point ray caster, when asked for a projection: the box of
        // voxel centres, and samples anchored on the near plane (#659).
        bool anchored = p.size.w != 0 && mode != 0;
        bool hit = intersectBox(vo, vd, anchored ? float3(0.0) : float3(-0.5), anchored ? dims - 1.0 : dims - 0.5,
                                tEntry, tExit);
        if (hit && p.cropMin.w != 0.0) {
            // The crop box is axis-aligned in voxel index space, as the host's
            // cropping widget is; it need not be axis-aligned in the world.
            float cEntry, cExit;
            hit = intersectBox(vo, vd, p.cropMin.xyz, p.cropMax.xyz, cEntry, cExit);
            tEntry = max(tEntry, cEntry); tExit = min(tExit, cExit);
            hit = hit && tExit >= tEntry;
        }
        // The crop's planes (#664), as VTK's ray caster applies them: the ray's
        // segment starts where it enters a plane's kept side and ends where it
        // leaves it, and is empty when it lies wholly outside a plane.
        for (uint i = 0; hit && i < p.clipping.x; ++i) {
            float4 plane = p.planes[i];
            float facing = dot(plane.xyz, vd), offset = dot(plane.xyz, vo) + plane.w;
            if (facing == 0.0) { hit = offset >= 0.0; continue; }
            float t = -offset / facing;
            if (facing > 0.0) tEntry = max(tEntry, t); else tExit = min(tExit, t);
            hit = tExit >= tEntry;
        }
        // Clipping range: distances along the viewing direction from the eye.
        float along = dot(direction, p.forward.xyz);
        float eyeOffset = dot(origin - p.eye.xyz, p.forward.xyz);
        float tNear = (p.clip.x - eyeOffset) / along, tFar = (p.clip.y - eyeOffset) / along;
        float tStart = max(max(tEntry, tNear), 0.0), tEnd = min(tExit, tFar);
        if (anchored) tStart = tNear + (floor((max(tEntry, tNear) - tNear) / p.clip.w) + 1.0) * p.clip.w;
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
                // VTK stores a position as round(v * 32767) and reads it back
                // with a 15-bit shift: its samples sit at v * 32767 / 32768.
                if (anchored) v *= 32767.0 / 32768.0;
                #if VOLUME_EMPTY_SPACE_SKIP
                if (mode == 0 || ((mode == 1 || mode == 2) && counted > 0)) {
                    uint3 grid = (uint3(dims) + 7) / 8;
                    int3 brick = clamp(int3(floor(v / 8.0)), int3(0), int3(grid) - 1);
                    float2 values = brickRanges[(brick.z * grid.y + brick.y) * grid.x + brick.x];
                    bool unchanged;
                    if (mode == 0) {
                        uint lo = uint(clamp((values.x - minimum) / p.window.y, 0.0, 1.0) * 255.0 + 0.5);
                        uint hi = uint(clamp((values.y - minimum) / p.window.y, 0.0, 1.0) * 255.0 + 0.5);
                        unchanged = opacityPrefix[hi + 1] == opacityPrefix[lo];
                    } else {
                        // A brick that cannot raise the maximum, or lower the
                        // minimum, changes nothing: VTK's MIP leaps such cells
                        // too (#659). The mean counts every sample.
                        unchanged = mode == 1 ? values.y <= reduced : values.x >= reduced;
                    }
                    if (unchanged) {
                        // Keep the original ray's sampling phase and stop before the boundary.
                        float exitDistance = INFINITY;
                        for (int axis = 0; axis < 3; ++axis) {
                            if (fabs(vd[axis]) < 1e-12) continue;
                            float face = float((brick[axis] + (vd[axis] > 0 ? 1 : 0)) * 8);
                            exitDistance = min(exitDistance, max(0.0, (face - v[axis]) / vd[axis]));
                        }
                        uint advance = uint(min(float(steps - s), max(1.0, floor(exitDistance / step))));
                        s += advance - 1;
                        continue;
                    }
                }
                #endif
                bool inside;
                // Quantitative projections retain explicit float interpolation;
                // a projection sampled as VTK's ray caster takes the hardware
                // filter, whose fixed-point weights stand where VTK's 15-bit
                // ones do (#659).
                float scalar = sampleVolume(volume, v, inside, mode == 0 || anchored);
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
                        float gx = sampleVolume(volume, v + float3(1, 0, 0), i0, true) - sampleVolume(volume, v - float3(1, 0, 0), i1, true);
                        float gy = sampleVolume(volume, v + float3(0, 1, 0), i2, true) - sampleVolume(volume, v - float3(0, 1, 0), i3, true);
                        float gz = sampleVolume(volume, v + float3(0, 0, 1), i4, true) - sampleVolume(volume, v - float3(0, 0, 1), i5, true);
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
    private let brickPipeline: MTLComputePipelineState
    /// How uploads and renders reach the GPU (#623); the kernels and their results are the same on either.
    public let backend: MetalComputeBackend
    private let submitter: Metal4ComputeSubmitter?
    /// The Metal 4 submission slots: made, in flight and idle; nil on Metal 3.
    var submissionSlots: (made: Int, inFlight: Int, idle: Int)? { submitter?.slots }
    private var brickRanges: MTLBuffer?
    private var texture: MTLTexture?
    /// On Metal 4, a residency set holding the installed volume and its bounds, used by every pass on them (#623).
    private var volumeResidency: MTLResidencySet?
    private var volumeResidentResources: Set<ObjectIdentifier> = []
    private var uploaded: ResliceVolume?
    private var outputBuffer: MTLBuffer?, scalarBuffer: MTLBuffer?
    public private(set) var volumeBytes = 0
    // The transfer function on the GPU (#621), kept while its colours or opacities stay the same: a frame that
    // moves only the camera, the window or the crop makes nothing. A change makes new objects rather than
    // writing into ones a command buffer may still read. One of each is kept, so switching presets does not
    // grow anything; release() drops them.
    private var colourTable: (colour: Data, texture: MTLTexture)?
    private var opacityTable: (opacity: [Float], values: MTLBuffer, prefix: MTLBuffer)?
    /// CLUT textures and opacity buffers made so far.
    public private(set) var colourTableUploads = 0, opacityTableUploads = 0

    public init(device: MTLDevice, hardwareFiltering: Bool = true, emptySpaceSkipping: Bool = true,
                backend: MetalComputeBackend = .metal3) throws {
        let traceStart = MetalPerformanceTrace.now()
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw ResliceFailure.device("Metal cannot create a command queue.") }
        self.queue = queue
        self.backend = backend
        submitter = backend == .metal4
            ? try Metal4ComputeSubmitter.shared(for: device)
            : nil
        // Compiled once per device and option combination, shared with every other VR engine (#622). Hardware
        // filtering enters the key as the device resolves it.
        let (pipelines, compiled) = try MetalComputePipelineCache.pipelines(
            device: device,
            configuration: MetalComputePipelineCache.Configuration(
                source: Self.shader,
                macros: ["VOLUME_HARDWARE_FILTERING": hardwareFiltering && device.supports32BitFloatFiltering,
                         "VOLUME_EMPTY_SPACE_SKIP": emptySpaceSkipping],
                functions: ["volumeRender", "volumeBrickRanges"]))
        pipeline = pipelines["volumeRender"]!
        brickPipeline = pipelines["volumeBrickRanges"]!
        MetalPerformanceTrace.record("vr.pipeline", startedAt: traceStart, extra: ["cold": compiled])
    }

    public var isReady: Bool { texture != nil }

    /// Same refusal as the MPR engine: named dimensions, no silent reduction.
    public func memoryRequirement(width: Int, height: Int, depth: Int) throws -> Int {
        try MPRMetalReslicer.memoryRequirement(device: device, width: width, height: height, depth: depth)
    }

    public func upload(_ volume: ResliceVolume) throws {
        let traceStart = MetalPerformanceTrace.now()
        let (texture, bytes) = try MPRMetalReslicer.makeTexture(device: device, volume: volume)
        let grid = SIMD3((volume.width + 7) / 8, (volume.height + 7) / 8, (volume.depth + 7) / 8)
        guard let ranges = device.makeBuffer(length: grid.x * grid.y * grid.z * 8, options: .storageModePrivate)
        else { throw ResliceFailure.memory("Metal refused the volume bounds.") }
        if let submitter {
            // Metal 4 (#623): the bounds pass is its own submission, finished before any render reads them. The
            // volume and its bounds go into one residency set that every pass on them uses; residency is not
            // requested at once, which made opening slower than on Metal 3.
            let residency = try device.makeResidencySet(descriptor: MTLResidencySetDescriptor())
            residency.addAllocation(texture); residency.addAllocation(ranges)
            residency.commit()
            let times: Metal4ComputeSubmitter.Times
            do {
                times = try submitter.dispatch(pipeline: brickPipeline, textures: [texture], buffers: [ranges], uniformsIndex: nil,
                                               parameters: UnsafeRawBufferPointer(start: nil, count: 0),
                                               size: MTLSize(width: grid.x, height: grid.y, depth: grid.z),
                                               threadsPerThreadgroup: MTLSize(width: 128, height: 1, depth: 1), groups: true,
                                               resident: residency, residentResources: [ObjectIdentifier(texture), ObjectIdentifier(ranges)])
            } catch {
                MetalPerformanceTrace.record("vr.upload.metal4", startedAt: traceStart, committedAt: nil, completedAt: nil,
                                             gpuStartTime: 0, gpuEndTime: 0, failed: true, finishedAt: nil)
                throw error
            }
            MetalPerformanceTrace.record("vr.upload.metal4", startedAt: traceStart, committedAt: times.committedAt,
                                         completedAt: times.observedAt, gpuStartTime: times.gpuStartTime,
                                         gpuEndTime: times.gpuEndTime, failed: false, finishedAt: times.observedAt,
                                         extra: ["bytes": bytes])
            brickRanges = ranges
            self.texture = texture; uploaded = volume; volumeBytes = bytes
            volumeResidency = residency
            volumeResidentResources = [ObjectIdentifier(texture), ObjectIdentifier(ranges)]
            return
        }
        guard let command = queue.makeCommandBuffer(), let encoder = command.makeComputeCommandEncoder()
        else { throw ResliceFailure.memory("Metal refused the volume bounds.") }
        encoder.setComputePipelineState(brickPipeline)
        encoder.setTexture(texture, index: 0); encoder.setBuffer(ranges, offset: 0, index: 0)
        encoder.dispatchThreadgroups(MTLSize(width: grid.x, height: grid.y, depth: grid.z), threadsPerThreadgroup: MTLSize(width: 128, height: 1, depth: 1))
        encoder.endEncoding()
        let committedAt = MetalPerformanceTrace.now()
        command.commit(); command.waitUntilCompleted()
        let completedAt = MetalPerformanceTrace.now()
        MetalPerformanceTrace.record("vr.upload", startedAt: traceStart, committedAt: committedAt, completedAt: completedAt,
                                     command: command, finishedAt: completedAt, extra: ["bytes": bytes])
        guard command.status == .completed else { throw command.error ?? ResliceFailure.device("The volume bounds failed.") }
        brickRanges = ranges
        self.texture = texture; uploaded = volume; volumeBytes = bytes
    }

    public func release() {
        texture = nil; uploaded = nil; volumeBytes = 0; volumeResidency = nil; volumeResidentResources = []
        outputBuffer = nil; scalarBuffer = nil
        brickRanges = nil
        colourTable = nil; opacityTable = nil
    }

    /// The CLUT texture of `colour`, made only when the colours differ from the kept one.
    private func colourTexture(for colour: Data) throws -> MTLTexture {
        if let kept = colourTable, kept.colour == colour { return kept.texture }
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba8Unorm, width: 256, height: 1, mipmapped: false)
        descriptor.storageMode = .shared; descriptor.usage = .shaderRead
        guard let texture = device.makeTexture(descriptor: descriptor) else { throw ResliceFailure.device("Metal refused the colour table.") }
        colour.withUnsafeBytes { bytes in
            texture.replace(region: MTLRegionMake2D(0, 0, 256, 1), mipmapLevel: 0, withBytes: bytes.baseAddress!, bytesPerRow: 1024)
        }
        colourTable = (colour, texture)
        colourTableUploads += 1
        return texture
    }

    /// The opacities and their running count of non-zero entries (the kernel's empty-space test), made only
    /// when the opacities differ from the kept ones.
    private func opacityBuffers(for opacity: [Float]) throws -> (values: MTLBuffer, prefix: MTLBuffer) {
        if let kept = opacityTable, kept.opacity == opacity { return (kept.values, kept.prefix) }
        var prefix: [UInt32] = [0]
        prefix.reserveCapacity(opacity.count + 1)
        for alpha in opacity { prefix.append(prefix.last! + (alpha > 0 ? 1 : 0)) }
        guard let values = device.makeBuffer(bytes: opacity, length: 256 * 4, options: .storageModeShared),
              let counts = device.makeBuffer(bytes: prefix, length: prefix.count * MemoryLayout<UInt32>.stride, options: .storageModeShared)
        else { throw ResliceFailure.memory("Metal refused the opacity table.") }
        opacityTable = (opacity, values, counts)
        opacityTableUploads += 1
        return (values, counts)
    }

    struct Params {
        var worldToVoxel: simd_float4x4, voxelToWorld: simd_float4x4
        var eye: SIMD4<Float>, forward: SIMD4<Float>, right: SIMD4<Float>, up: SIMD4<Float>
        var clip: SIMD4<Float>, window: SIMD4<Float>, shading: SIMD4<Float>
        var cropMin: SIMD4<Float>, cropMax: SIMD4<Float>, background: SIMD4<Float>
        var size: SIMD4<UInt32>
        var viewport: SIMD4<UInt32>
        var planes: (SIMD4<Float>, SIMD4<Float>, SIMD4<Float>, SIMD4<Float>, SIMD4<Float>, SIMD4<Float>)
        var clipping: SIMD4<UInt32>
    }

    public func render(_ request: VolumeRenderRequest) throws -> VolumeRenderResult {
        let traceStart = MetalPerformanceTrace.now()
        guard let texture, let uploaded, let brickRanges else { throw ResliceFailure.device("No volume is uploaded.") }
        let count = request.width * request.height
        if (outputBuffer?.length ?? 0) < count * 4 || (scalarBuffer?.length ?? 0) < count * 4 {
            outputBuffer = device.makeBuffer(length: count * 4, options: .storageModeShared)
            scalarBuffer = device.makeBuffer(length: count * 4, options: .storageModeShared)
        }
        guard let output = outputBuffer, let scalar = scalarBuffer
        else { throw ResliceFailure.memory("Metal refused a \(VolumeAllocation.describe(byteCount: count * 8)) image.") }
        let clut = try colourTexture(for: request.transfer.colour)
        let opacity = try opacityBuffers(for: request.transfer.opacity)
        let camera = request.camera
        let aspect = Float(request.viewportSize.x) / Float(request.viewportSize.y)
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
            size: SIMD4(UInt32(request.width), UInt32(request.height), maxSteps, request.anchoredProjection ? 1 : 0),
            viewport: SIMD4(UInt32(request.viewportSize.x), UInt32(request.viewportSize.y),
                            UInt32(request.viewportOrigin.x), UInt32(request.viewportOrigin.y)),
            planes: (.zero, .zero, .zero, .zero, .zero, .zero),
            clipping: SIMD4(UInt32(request.clippingPlanes.count), 0, 0, 0))
        withUnsafeMutableBytes(of: &params.planes) { raw in
            for (index, plane) in request.clippingPlanes.enumerated() { raw.storeBytes(of: plane, toByteOffset: index * 16, as: SIMD4<Float>.self) }
        }
        if let submitter {
            // Metal 4 (#623): the slot's uniforms carry the parameters; the images are copied after the feedback.
            let started = DispatchTime.now().uptimeNanoseconds
            let times: Metal4ComputeSubmitter.Times
            do {
                times = try withUnsafeBytes(of: &params) { parameters in
                    try submitter.dispatch(pipeline: pipeline, textures: [texture, clut],
                                           buffers: [opacity.values, output, scalar, nil, brickRanges, opacity.prefix],
                                           uniformsIndex: 3, parameters: parameters,
                                           size: MTLSize(width: request.width, height: request.height, depth: 1),
                                           threadsPerThreadgroup: MTLSize(width: 8, height: 8, depth: 1),
                                           resident: volumeResidency, residentResources: volumeResidentResources)
                }
            } catch {
                MetalPerformanceTrace.record("vr.render.metal4", startedAt: traceStart, committedAt: nil, completedAt: nil,
                                             gpuStartTime: 0, gpuEndTime: 0, failed: true, finishedAt: nil)
                throw error
            }
            let milliseconds = Double(DispatchTime.now().uptimeNanoseconds - started) / 1e6
            let result = VolumeRenderResult(bgra: Data(bytes: output.contents(), count: count * 4),
                                            scalar: Data(bytes: scalar.contents(), count: count * 4),
                                            milliseconds: milliseconds)
            MetalPerformanceTrace.record("vr.render.metal4", startedAt: traceStart, committedAt: times.committedAt,
                                         completedAt: times.observedAt, gpuStartTime: times.gpuStartTime,
                                         gpuEndTime: times.gpuEndTime, failed: false, finishedAt: MetalPerformanceTrace.now(),
                                         extra: ["width": request.width, "height": request.height])
            return result
        }
        guard let command = queue.makeCommandBuffer(), let encoder = command.makeComputeCommandEncoder() else {
            throw ResliceFailure.device("Metal cannot encode the volume render.")
        }
        let started = DispatchTime.now().uptimeNanoseconds
        encoder.setComputePipelineState(pipeline)
        encoder.setTexture(texture, index: 0); encoder.setTexture(clut, index: 1)
        encoder.setBuffer(opacity.values, offset: 0, index: 0); encoder.setBuffer(output, offset: 0, index: 1)
        encoder.setBuffer(scalar, offset: 0, index: 2)
        encoder.setBytes(&params, length: MemoryLayout<Params>.stride, index: 3)
        encoder.setBuffer(brickRanges, offset: 0, index: 4)
        encoder.setBuffer(opacity.prefix, offset: 0, index: 5)
        let w = 8, h = 8
        encoder.dispatchThreads(MTLSize(width: request.width, height: request.height, depth: 1),
                                threadsPerThreadgroup: MTLSize(width: w, height: h, depth: 1))
        encoder.endEncoding()
        let committedAt = MetalPerformanceTrace.now()
        command.commit(); command.waitUntilCompleted()
        let completedAt = MetalPerformanceTrace.now()
        guard command.status == .completed else {
            MetalPerformanceTrace.record("vr.render", startedAt: traceStart, committedAt: committedAt,
                                         completedAt: completedAt, command: command)
            throw command.error ?? ResliceFailure.device("The volume render failed.")
        }
        let milliseconds = Double(DispatchTime.now().uptimeNanoseconds - started) / 1e6
        let result = VolumeRenderResult(bgra: Data(bytes: output.contents(), count: count * 4),
                                        scalar: Data(bytes: scalar.contents(), count: count * 4),
                                        milliseconds: milliseconds)
        MetalPerformanceTrace.record("vr.render", startedAt: traceStart, committedAt: committedAt, completedAt: completedAt,
                                     command: command, finishedAt: MetalPerformanceTrace.now(),
                                     extra: ["width": request.width, "height": request.height])
        return result
    }
}

/// Objective-C face for `VRHostBridge.mm`. Vectors travel as number arrays.
@objc(HorosVolumeRenderer)
public final class VolumeRendererBridge: NSObject {
    private let engine: VolumeMetalRenderer
    @objc public private(set) var lastMilliseconds: Double = 0
    // The host sends its opacity curve with every frame; the table is recomputed only when the points change,
    // and the kept table lets the engine recognise its opacities without comparing them (#621).
    private var opacityCurve: (points: [NSNumber], table: [Float])?

    private init(engine: VolumeMetalRenderer) { self.engine = engine; super.init() }

    /// `[HorosVolumeRenderer makeAndReturnError:]` from Objective-C, on the backend the host asks for (#623).
    @objc public static func make() throws -> VolumeRendererBridge {
        guard let device = MTLCreateSystemDefaultDevice() else { throw ResliceFailure.device("No Metal device is available.").nsError }
        return try make(device: device, backend: MetalComputeBackend.host(device: device).backend)
    }

    public static func make(device: MTLDevice, backend: MetalComputeBackend) throws -> VolumeRendererBridge {
        do { return VolumeRendererBridge(engine: try VolumeMetalRenderer(device: device, backend: backend)) }
        catch let failure as ResliceFailure { throw failure.nsError }
    }

    /// "Metal 3" or "Metal 4".
    @objc public var backendName: String { engine.backend.name }

    @objc public var isReady: Bool { engine.isReady }
    @objc public var volumeBytes: Int { engine.volumeBytes }
    @objc public var colourTableUploads: Int { engine.colourTableUploads }
    @objc public var opacityTableUploads: Int { engine.opacityTableUploads }
    @objc public func releaseVolume() { engine.release(); opacityCurve = nil }

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

    /// The picture VTK's ray caster makes of a projection (#659), from the
    /// reduced scalars: `VTKKWRCHelper_LookupColorMax` writes the colour of the
    /// value premultiplied by the scalar opacity at that value, both in 15 bits,
    /// and outside composite blending VTK does not correct that opacity for the
    /// step. The functions are the host's: the colour is `BuildFunctionFromTable`
    /// over the window with 255 entries (entries 0...254 of the CLUT, linear
    /// between them), the opacity is the curve's points over the window, linear
    /// between them, with (0, 0) before a curve that starts later and (256, 1)
    /// after one that ends earlier, both clamped outside. A ray with no sample
    /// (`background`) stays at zero, as VTK leaves it. Four UInt16 per pixel,
    /// premultiplied RGBA, in the scalars' order.
    /// How many crop planes a render takes (#664).
    @objc public static let maximumClippingPlanes = VolumeRenderRequest.maximumClippingPlanes

    @objc public static func projectionPicture(scalar: NSData, level: Double, width windowWidth: Double, clut: NSData,
                                               opacityPoints: [NSNumber], background: Double) -> NSData {
        var curve = [SIMD2<Double>]()
        var index = 0
        while index + 1 < opacityPoints.count {
            curve.append(SIMD2(opacityPoints[index].doubleValue, opacityPoints[index + 1].doubleValue)); index += 2
        }
        curve = curve.filter { $0.x.isFinite && $0.y.isFinite }.sorted { $0.x < $1.x }
        if curve.first.map({ $0.x != 0 }) ?? true { curve.insert(SIMD2(0, 0), at: 0) }
        if curve.last!.x != 256 { curve.append(SIMD2(256, 1)) }
        func opacity(_ x: Double) -> Double {
            if x <= curve[0].x { return curve[0].y }
            for (previous, next) in zip(curve, curve.dropFirst()) where x <= next.x {
                let span = next.x - previous.x
                return span > 0 ? previous.y + (next.y - previous.y) * (x - previous.x) / span : next.y
            }
            return curve.last!.y
        }
        let colours = [UInt8](clut as Data)
        let values = [Float](unsafeUninitializedCapacity: scalar.length / 4) { buffer, count in
            count = scalar.length / 4
            _ = scalar.getBytes(buffer.baseAddress!, length: count * 4)
        }
        let start = level - windowWidth / 2
        var picture = [UInt16](repeating: 0, count: values.count * 4)
        guard colours.count == 1024, windowWidth > 0 else { return Data() as NSData }
        for (pixel, value) in values.enumerated() where Double(value) != background && value.isFinite {
            let fraction = min(1, max(0, (Double(value) - start) / windowWidth))
            let alpha = UInt32(min(1, max(0, opacity(fraction * 256))) * 32767 + 0.5)
            let position = fraction * 254, lower = Int(position), upper = min(254, lower + 1), weight = position - Double(lower)
            for channel in 0..<3 {
                let colour = (Double(colours[4 * lower + channel]) * (1 - weight) + Double(colours[4 * upper + channel]) * weight) / 255
                let fixed = UInt32(colour * 32767 + 0.5)
                picture[4 * pixel + channel] = UInt16((fixed * alpha + 0x7fff) >> 15)
            }
            picture[4 * pixel + 3] = UInt16(alpha)
        }
        return picture.withUnsafeBytes { Data($0) } as NSData
    }

    @objc public func memoryRequirementForWidth(_ width: Int, height: Int, depth: Int) throws -> NSNumber {
        do { return NSNumber(value: try engine.memoryRequirement(width: width, height: height, depth: depth)) }
        catch let failure as ResliceFailure { throw failure.nsError }
    }

    /// Renders BGRA bytes. `camera` is position(3), focal(3), viewUp(3),
    /// parallel(1), parallelScale(1), viewAngle(1); a negative `far` means no
    /// clipping range. `opacityPoints` are the host's x/y pairs (x in 0…256).
    /// `crop` is minX, minY, minZ, maxX, maxY, maxZ in voxel index units, or empty.
    /// `anchoredProjection` samples a projection as the host's VTK ray caster
    /// does (#659); composite ignores it. `clippingPlanes` are four numbers per
    /// plane in voxel index coordinates, a·v + d ≥ 0 kept, at most six (#664).
    @objc public func render(camera: [NSNumber], near: Double, far: Double, level: Double, width windowWidth: Double, clut: NSData,
                             opacityPoints: [NSNumber], mode: Int, shading: [NSNumber], crop: [NSNumber],
                             clippingPlanes: [NSNumber] = [], width: Int, height: Int,
                             sampleStep: Double, scalarBackground: Double, anchoredProjection: Bool = false,
                             imageRegion: [NSNumber] = [], scalarOut: NSMutableData?) throws -> NSData {
        guard camera.count == 12, shading.count == 5, crop.isEmpty || crop.count == 6, clippingPlanes.count % 4 == 0,
              imageRegion.isEmpty || imageRegion.count == 4, let renderingMode = VolumeRenderingMode(rawValue: mode) else {
            throw ResliceFailure.geometry("The render description is incomplete.").nsError
        }
        return try renderFull(camera: camera + [NSNumber(value: near), NSNumber(value: far)], level: level, windowWidth: windowWidth,
                              clut: clut, opacityPoints: opacityPoints, renderingMode: renderingMode, shading: shading, crop: crop,
                              width: width, height: height, sampleStep: sampleStep, scalarBackground: Float(scalarBackground),
                              anchoredProjection: anchoredProjection, clippingPlanes: clippingPlanes,
                              imageRegion: imageRegion, scalarOut: scalarOut)
    }

    private func renderFull(camera: [NSNumber], level: Double, windowWidth: Double, clut: NSData, opacityPoints: [NSNumber],
                            renderingMode: VolumeRenderingMode, shading: [NSNumber], crop: [NSNumber], width: Int, height: Int,
                            sampleStep: Double, scalarBackground: Float, anchoredProjection: Bool = false,
                            clippingPlanes: [NSNumber] = [], imageRegion: [NSNumber], scalarOut: NSMutableData?) throws -> NSData {
        let c = camera.map { $0.floatValue }
        do {
            let far = c.count > 13 ? c[13] : -1
            let volumeCamera = try VolumeCamera(position: SIMD3(c[0], c[1], c[2]), focalPoint: SIMD3(c[3], c[4], c[5]),
                                                viewUp: SIMD3(c[6], c[7], c[8]), parallel: c[9] != 0, parallelScale: c[10],
                                                viewAngle: c[11], clippingRange: far < 0 ? nil : SIMD2(max(0, c[12]), far))
            let table: [Float]
            if let kept = opacityCurve, kept.points == opacityPoints {
                table = kept.table
            } else {
                var points = [SIMD2<Float>]()
                var index = 0
                while index + 1 < opacityPoints.count {
                    points.append(SIMD2(opacityPoints[index].floatValue, opacityPoints[index + 1].floatValue)); index += 2
                }
                table = VolumeTransferFunction.opacityTable(points: points)
                opacityCurve = (opacityPoints, table)
            }
            let transfer = try VolumeTransferFunction(level: Float(level), width: Float(windowWidth), colour: clut as Data,
                                                      opacity: table)
            let s = shading.map { $0.floatValue }
            let volumeShading = VolumeShading(enabled: s[0] != 0, ambient: s[1], diffuse: s[2], specular: s[3], specularPower: s[4])
            let cropBox: (minimum: SIMD3<Float>, maximum: SIMD3<Float>)? = crop.isEmpty ? nil :
                (SIMD3(crop[0].floatValue, crop[1].floatValue, crop[2].floatValue), SIMD3(crop[3].floatValue, crop[4].floatValue, crop[5].floatValue))
            let request = try VolumeRenderRequest(camera: volumeCamera, transfer: transfer, mode: renderingMode, shading: volumeShading,
                                                  crop: cropBox, width: width, height: height, sampleStep: Float(sampleStep),
                                                  scalarBackground: scalarBackground.isFinite ? scalarBackground : nil,
                                                  viewportSize: imageRegion.isEmpty ? nil : SIMD2(imageRegion[0].intValue, imageRegion[1].intValue),
                                                  viewportOrigin: imageRegion.isEmpty ? .zero : SIMD2(imageRegion[2].intValue, imageRegion[3].intValue),
                                                  anchoredProjection: anchoredProjection,
                                                  clippingPlanes: stride(from: 0, to: clippingPlanes.count, by: 4).map { index in
                                                      SIMD4((0..<4).map { clippingPlanes[index + $0].floatValue }) })
            let result = try engine.render(request)
            lastMilliseconds = result.milliseconds
            if let scalarOut { scalarOut.setData(result.scalar) }
            return result.bgra as NSData
        } catch let failure as ResliceFailure { throw failure.nsError }
    }
}
