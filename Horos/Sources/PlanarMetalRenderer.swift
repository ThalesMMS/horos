import Foundation
import Metal
import Accelerate

/// Immutable presentation of already decoded host pixels. Coordinates are
/// supplied by DCMView/N3Geometry, not recomputed from DICOM by this renderer.
struct PlanarFrame: Equatable {
    let width: Int, height: Int
    let pixels: Data, clut: Data
    let identifier: String
    let background: Float
    let softwareScale: Int
    var mapping: SIMD4<Float>
    var geometry: SIMD4<Float>
    var window: SIMD4<Float>

    init(_ value: NSDictionary) throws {
        func fail() -> NSError { NSError(domain: "HorosPlanar", code: 1,
            userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("The image cannot be compared in Metal. Use the original viewer.", comment: "")]) }
        guard let w = value["width"] as? NSNumber, let h = value["height"] as? NSNumber,
              let data = value["pixels"] as? Data, let table = value["clut"] as? Data,
              let id = value["frameIdentity"] as? String, !id.isEmpty,
              let points = value["screenToPixel"] as? [NSNumber], points.count == 6,
              let size = value["viewSize"] as? [NSNumber], size.count == 2,
              let level = value["level"] as? NSNumber, let ww = value["widthWindow"] as? NSNumber
        else { throw fail() }
        width = w.intValue; height = h.intValue
        guard width > 0, height > 0, width <= 16384, height <= 16384,
              VolumeAllocation.byteCount(width: width, height: height, slices: 1, bytesPerVoxel: 4) == data.count,
              table.count == 1024, points.allSatisfy({ $0.floatValue.isFinite }),
              size.allSatisfy({ $0.floatValue.isFinite && $0.floatValue > 0 }),
              level.floatValue.isFinite, ww.floatValue.isFinite, abs(ww.floatValue) > 0
        else { throw fail() }
        pixels = data; clut = table; identifier = id
        background = (value["background"] as? NSNumber)?.boolValue == true ? 1 : 0
        softwareScale = (value["softwareScale"] as? NSNumber)?.intValue ?? 1
        guard (1...3).contains(softwareScale), width * softwareScale <= 16384,
              height * softwareScale <= 16384,
              data.count <= 512 * 1024 * 1024 / (softwareScale * softwareScale)
        else { throw fail() }
        mapping = SIMD4(points[0].floatValue, points[1].floatValue,
                        points[2].floatValue - points[0].floatValue,
                        points[3].floatValue - points[1].floatValue)
        geometry = SIMD4(points[4].floatValue - points[0].floatValue,
                         points[5].floatValue - points[1].floatValue, size[0].floatValue, size[1].floatValue)
        window = SIMD4(level.floatValue, ww.floatValue,
                       (value["isColor"] as? NSNumber)?.boolValue == true ? 1 : 0,
                       (value["nearest"] as? NSNumber)?.boolValue == true ? 1 : 0)
        guard softwareScale == 1 || (window.z == 0 && window.w == 0) else { throw fail() }
        guard [mapping.x,mapping.y,mapping.z,mapping.w,geometry.x,geometry.y,geometry.z,geometry.w,
               window.x-window.y*0.5].allSatisfy({ $0.isFinite }) else { throw fail() }
        if window.z != 0 {
            let span = ((window.x + window.y*0.5) - (window.x - window.y*0.5)).rounded(.towardZero)
            guard span.isFinite, abs(span) >= 1 else { throw fail() }
        }
    }

    /// Match the host's optional vImage scalar enlargement, retaining float
    /// intensities through both resampling stages. CLUT and windowing follow
    /// the final GPU sample; the source used by ROI measurements stays intact.
    func texturePixels() throws -> Data {
        if softwareScale == 1 { return pixels }
        let w = width * softwareScale, h = height * softwareScale
        var result = Data(count: w * h * 4)
        let status = result.withUnsafeMutableBytes { destination in
            pixels.withUnsafeBytes { source in
                var input = vImage_Buffer(data: UnsafeMutableRawPointer(mutating: source.baseAddress!),
                    height: vImagePixelCount(height), width: vImagePixelCount(width), rowBytes: width * 4)
                var output = vImage_Buffer(data: destination.baseAddress!,
                    height: vImagePixelCount(h), width: vImagePixelCount(w), rowBytes: w * 4)
                return vImageScale_PlanarF(&input, &output, nil, vImage_Flags(kvImageNoFlags))
            }
        }
        guard status == kvImageNoError else { throw PlanarMetalRenderer.failure() }
        return result
    }
}

/// The scalar sampling -> window -> CLUT order follows the planar fragment in
/// ystarrev/horos MetalShaders.metal at 23722fb552d96fa2d60c7f58a6d4ac2c27950f86.
/// Host decoding, geometry and sessions are deliberately not imported from it.
final class PlanarMetalRenderer {
    static let shader = #"""
    #include <metal_stdlib>
    using namespace metal;
    struct Params { float4 mapping; float4 geometry; float4 window; float4 output; };
    struct Vertex { float4 position [[position]]; };
    vertex Vertex planarVertex(uint id [[vertex_id]]) {
        const float2 p[] = {float2(-1,-1),float2(3,-1),float2(-1,3)};
        Vertex v; v.position=float4(p[id],0,1); return v;
    }
    fragment float4 planarFragment(Vertex in [[stage_in]], constant Params &p [[buffer(0)]],
        texture2d<float> image [[texture(0)]], texture2d<float, access::read> clut [[texture(1)]]) {
        float scale=min(p.output.x/p.geometry.z,p.output.y/p.geometry.w);
        float2 size=p.geometry.zw*scale;
        float2 point=(in.position.xy-(p.output.xy-size)*0.5)/size;
        if(any(point<0.0)||any(point>=1.0))return float4(p.output.zzz,1);
        float2 pixel=p.mapping.xy+point.x*p.mapping.zw+point.y*p.geometry.xy;
        float2 dimensions=float2(image.get_width(),image.get_height())/p.output.w;
        if(any(pixel<0.0)||any(pixel>=dimensions))return float4(p.output.zzz,1);
        constexpr sampler linearSampler(coord::normalized,address::clamp_to_edge,filter::linear);
        constexpr sampler nearestSampler(coord::normalized,address::clamp_to_edge,filter::nearest);
        float4 sampled;
        if(p.window.w != 0) sampled=image.sample(nearestSampler,pixel/dimensions);
        else if(p.window.z != 0) sampled=image.sample(linearSampler,pixel/dimensions);
        else {
            // Hardware sampler weights can be quantized. Compute scalar
            // weights in float so an oblique sample does not jump across a
            // discrete CLUT boundary solely because of sampler precision.
            float2 xy=pixel*p.output.w-0.5;
            int2 base=int2(floor(xy)), last=int2(image.get_width()-1,image.get_height()-1);
            float2 weight=fract(xy);
            float a=image.read(uint2(clamp(base,int2(0),last))).r;
            float b=image.read(uint2(clamp(base+int2(1,0),int2(0),last))).r;
            float c=image.read(uint2(clamp(base+int2(0,1),int2(0),last))).r;
            float d=image.read(uint2(clamp(base+int2(1,1),int2(0),last))).r;
            sampled=float4(mix(mix(a,b,weight.x),mix(c,d,weight.x),weight.y),0,0,1);
        }
        float minimum=p.window.x-p.window.y*0.5;
        if(p.window.z != 0) {
            // DCMPix's RGB conversion table truncates both its window span
            // (long diff = max-min) and each index before the discrete CLUT.
            float span=trunc((p.window.x+p.window.y*0.5)-minimum);
            float3 rgb=clamp((sampled.gba*255.0-minimum)*255.0/span,0.0,255.0);
            uint3 index=uint3(rgb);
            return float4(clut.read(uint2(index.r,0)).r,clut.read(uint2(index.g,0)).g,
                          clut.read(uint2(index.b,0)).b,1);
        }
        if(!isfinite(sampled.r))return float4(0,0,0,1);
        float normalized=clamp((sampled.r-minimum)/p.window.y,0.0,1.0);
        return float4(clut.read(uint2(uint(normalized*255.0+0.5),0)).rgb,1);
    }
    """#
    let device: MTLDevice
    let queue: MTLCommandQueue
    let pipeline: MTLRenderPipelineState
    private(set) var image: MTLTexture?
    private var clut: MTLTexture?
    private var frame: PlanarFrame?

    init(device: MTLDevice) throws {
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw Self.failure() }
        self.queue = queue
        let library = try device.makeLibrary(source: Self.shader, options: nil)
        let descriptor = MTLRenderPipelineDescriptor()
        descriptor.vertexFunction = library.makeFunction(name: "planarVertex")
        descriptor.fragmentFunction = library.makeFunction(name: "planarFragment")
        descriptor.colorAttachments[0].pixelFormat = .bgra8Unorm
        pipeline = try device.makeRenderPipelineState(descriptor: descriptor)
    }

    static func failure() -> NSError {
        NSError(domain: "HorosPlanar", code: 2, userInfo: [NSLocalizedDescriptionKey:
            NSLocalizedString("Metal comparison is unavailable. Use the original viewer.", comment: "")])
    }

    func update(_ frame: PlanarFrame) throws {
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(
            pixelFormat: frame.window.z == 0 ? .r32Float : .rgba8Unorm,
            width: frame.width * frame.softwareScale, height: frame.height * frame.softwareScale, mipmapped: false)
        descriptor.storageMode = .shared; descriptor.usage = .shaderRead
        let tableDescriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba8Unorm,
            width: 256, height: 1, mipmapped: false)
        tableDescriptor.storageMode = .shared; tableDescriptor.usage = .shaderRead
        guard let image = device.makeTexture(descriptor: descriptor),
              let table = device.makeTexture(descriptor: tableDescriptor) else { throw Self.failure() }
        let pixels = try frame.texturePixels()
        pixels.withUnsafeBytes { bytes in
            image.replace(region: MTLRegionMake2D(0,0,image.width,image.height), mipmapLevel: 0,
                          withBytes: bytes.baseAddress!, bytesPerRow: image.width*4)
        }
        frame.clut.withUnsafeBytes { bytes in
            table.replace(region: MTLRegionMake2D(0,0,256,1), mipmapLevel: 0,
                          withBytes: bytes.baseAddress!, bytesPerRow: 1024)
        }
        self.image = image; clut = table; self.frame = frame
    }

    /// All retained resources belong to this frame; a command buffer retains
    /// its own references until completion, including during cancellation.
    func clear() { image = nil; clut = nil; frame = nil }

    func encode(into target: MTLTexture, command: MTLCommandBuffer) throws {
        guard let frame, let image, let clut else { throw Self.failure() }
        let pass = MTLRenderPassDescriptor()
        pass.colorAttachments[0].texture = target
        pass.colorAttachments[0].loadAction = .clear; pass.colorAttachments[0].storeAction = .store
        pass.colorAttachments[0].clearColor = MTLClearColorMake(0,0,0,1)
        guard let encoder = command.makeRenderCommandEncoder(descriptor: pass) else { throw Self.failure() }
        var parameters = [frame.mapping, frame.geometry, frame.window,
                          SIMD4<Float>(Float(target.width), Float(target.height),frame.background,Float(frame.softwareScale))]
        encoder.setRenderPipelineState(pipeline)
        encoder.setFragmentBytes(&parameters, length: 4*MemoryLayout<SIMD4<Float>>.stride, index: 0)
        encoder.setFragmentTexture(image, index: 0); encoder.setFragmentTexture(clut, index: 1)
        encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
        encoder.endEncoding()
    }

    /// Shares the actual GPU path with the on-screen renderer; no CPU surrogate.
    func renderTexture(width: Int, height: Int) throws -> MTLTexture {
        guard width > 0, height > 0, width <= 16384, height <= 16384 else { throw Self.failure() }
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .bgra8Unorm,
            width: width, height: height, mipmapped: false)
        descriptor.storageMode = .shared; descriptor.usage = .renderTarget
        guard let target = device.makeTexture(descriptor: descriptor),
              let command = queue.makeCommandBuffer() else { throw Self.failure() }
        try encode(into: target, command: command)
        command.commit(); command.waitUntilCompleted()
        guard command.status == .completed else { throw command.error ?? Self.failure() }
        return target
    }

    func renderBGRA(width: Int, height: Int) throws -> Data {
        let target = try renderTexture(width: width, height: height)
        var result = Data(count: width*height*4)
        result.withUnsafeMutableBytes { bytes in
            target.getBytes(bytes.baseAddress!, bytesPerRow: width*4,
                            from: MTLRegionMake2D(0,0,width,height), mipmapLevel: 0)
        }
        return result
    }
}
