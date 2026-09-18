import Foundation
import Metal
import Accelerate
import simd

/// The opacity table the host applies after the window (#657).
///
/// For a scalar image `applyNonLinearWLWWThread:` (DCMPix.m) makes each 8-bit
/// display byte from the calibrated value, reading the image's own WL/WW:
///
///     from  = wl - ww/2                        evaluated in double, stored as float
///     ratio = 4096 / ww                        evaluated in double, stored as float
///     index = clamp(int(ratio * (value - from)), 0, 4095)
///     byte  = 255 * table[index]               truncated
///
/// and `compute8bitRepresentation` inverts the byte afterwards when the display
/// is inverted. `PlanarTransferPass` runs exactly that on the GPU, per source
/// pixel, before any interpolation: the original renderer interpolates these
/// bytes, never the calibrated values under a nonlinear table, and parity with
/// it is the acceptance. The fragment then reads the bytes as an already
/// windowed image, as the original's scalar CLUT program does, and applies the
/// CLUT.
///
/// A colour image takes the table in its 256-entry conversion instead
/// (`compute8bitRepresentation`, the RGB branch), which does not depend on the
/// pixel: it is composed into the CLUT here, so the fragment is unchanged.
struct PlanarTransfer: Equatable {
    /// The host's 4096 floats, unchanged.
    let table: Data
    let from: Float, ratio: Float
    let inverted: Bool

    init(table: Data, level: Float, width: Float, inverted: Bool) {
        self.table = table; self.inverted = inverted
        // The host's expressions, float operands promoted to double and the
        // result rounded back to float on assignment, as C does.
        from = Float(Double(level) - Double(width) / 2)
        ratio = Float(4096 / Double(width))
    }

    /// The RGB conversion's table step, `val = 255.*transferFunctionPtr[val*16]`
    /// on a `long` and clamped to 0...255. The product is double, as the host's
    /// is; a NaN converts to zero, as arm64's conversion does.
    static func rgbByte(_ value: Float) -> UInt8 {
        let product = 255 * Double(value)
        guard !product.isNaN else { return 0 }
        return UInt8(min(255, max(0, product.rounded(.towardZero))))
    }
}

/// The 2D viewer's thick slab in mean, maximum or minimum mode (#659): the
/// current slice and the ones `-[DCMPix computeThickSlab]` reduces with it.
///
/// The host keeps the current slice, then adds the next `stack - 1` slices in
/// its stack direction, skipping any past either end of the series, and reduces
/// in that order: `vDSP_vmax`/`vDSP_vmin`, or `vDSP_vadd` and a multiplication by
/// `1.0f / count`. `PlanarSlabProjection` runs the MPR's reduction over the same
/// slices in the same order, with IEEE arithmetic, so the projected image equals
/// the host's bit for bit. The volume-rendering slab (modes 4 and 5) is a
/// composite through VTK, not a reduction, and stays with the original renderer.
struct PlanarSlab: Equatable {
    let projection: ResliceProjection
    /// The other slices, after the current one, in the host's order.
    let others: Data
    /// All the slices reduced, the current one included.
    let count: Int

    /// DCMPix's `stackMode`: 1 mean, 2 maximum, 3 minimum.
    static func projection(stackMode: Int) -> ResliceProjection? {
        switch stackMode {
        case 1: return .mean
        case 2: return .maximum
        case 3: return .minimum
        default: return nil
        }
    }
}

/// The slices a 2D thick slab reduces, asked by the host bridge so the rule is
/// written once, here, and measured against `computeThickSlab` by
/// `tests/test-planar-thick-slab.py`.
@objc(HorosPlanarThickSlab)
public final class PlanarThickSlab: NSObject {
    /// The indices after `position`, in the host's order: `position ± i` for
    /// `i` in `1..<stack`, minus toward the start when `direction` is non-zero,
    /// and only those inside `0..<count`.
    @objc public static func sliceIndices(position: Int, stack: Int, direction: Int, count: Int) -> [NSNumber] {
        guard stack > 1 else { return [] }
        return (1..<stack).compactMap { offset -> NSNumber? in
            let index = direction != 0 ? position - offset : position + offset
            return index >= 0 && index < count ? NSNumber(value: index) : nil
        }
    }
}

/// Immutable presentation of already decoded host pixels. Coordinates are
/// supplied by DCMView/N3Geometry, not recomputed from DICOM by this renderer.
struct PlanarFrame: Equatable {
    let width: Int, height: Int
    let pixels: Data, clut: Data
    let identifier: String
    let background: Float
    let softwareScale: Int
    /// A scalar image's opacity table; nil without one, and for colour, whose
    /// table is already in `clut`.
    let transfer: PlanarTransfer?
    /// The thick slab reduced before the window and the table; nil for a
    /// single slice, which the host does not reduce either.
    let slab: PlanarSlab?
    /// The menu's convolution filter, run after the slab and before the window
    /// and the table; nil without one.
    let convolution: PlanarConvolution?
    /// The host's own 8-bit presentation (#662): with a subtraction or a DICOM
    /// shutter the host prepares these bytes - vImage's half-precision gamma or
    /// window conversion, the polarity, the shutter mask with the CLUT's black
    /// index - and the original renderer draws them. Slab, filter and table are
    /// already in them. One byte per pixel, four for colour; nil otherwise.
    /// Every colour image comes this way (#660): its windowed ARGB bytes.
    let hostBytes: Data?
    /// The table the host lays over a colour image's bytes before they are
    /// interpolated (#660): `vImageTableLookUp_ARGB8888` with the opaque alpha
    /// table and the CLUT, or the CLUT times the channel factors. Alpha, red,
    /// green and blue, 256 bytes each; nil when the host lays none.
    let colourTable: Data?
    var mapping: SIMD4<Float>
    var geometry: SIMD4<Float>
    var window: SIMD4<Float>
    /// The series fused over this one (#658), at most one: its own pixels,
    /// window and CLUT, the CLUT's fourth column the host's alpha table, and a
    /// mapping from this view to its pixels. The host draws it with
    /// `-[DCMView drawRectIn::::::]` after the image, blended source-alpha over
    /// it, through its scalar CLUT program. An array only because a struct
    /// cannot hold a value of its own type.
    private(set) var fusion: [PlanarFrame] = []

    init(_ value: NSDictionary) throws {
        func fail() -> NSError { NSError(domain: "HorosPlanar", code: 1,
            userInfo: [NSLocalizedDescriptionKey: NSLocalizedString("The image cannot be compared in Metal. Use the original viewer.", comment: "")]) }
        guard let w = value["width"] as? NSNumber, let h = value["height"] as? NSNumber,
              let data = value["pixels"] as? Data, var table = value["clut"] as? Data,
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
        let isColor = (value["isColor"] as? NSNumber)?.boolValue == true
        let nearest = (value["nearest"] as? NSNumber)?.boolValue == true
        var hostBytes: Data?
        if let bytes = value["hostBytes"] {
            guard let presented = bytes as? Data, presented.count == width * height * (isColor ? 4 : 1) else { throw fail() }
            hostBytes = presented
        }
        var colourTable: Data?
        if let tables = value["colourTable"] {
            guard isColor, hostBytes != nil, let bytes = tables as? Data, bytes.count == 1024 else { throw fail() }
            colourTable = bytes
        }
        var transfer: PlanarTransfer?
        if hostBytes == nil, let function = value["transferFunction"] {
            guard let floats = function as? Data, floats.count == 4096 * MemoryLayout<Float>.size,
                  let transferLevel = (value["transferLevel"] as? NSNumber)?.floatValue,
                  let transferWidth = (value["transferWidth"] as? NSNumber)?.floatValue,
                  transferLevel.isFinite, transferWidth.isFinite, transferWidth != 0
            else { throw fail() }
            if isColor {
                // The host maps each channel through T(L(value)) and then the
                // CLUT, so the CLUT entry the fragment reads for L is CLUT(T(L)).
                let composed = table
                floats.withUnsafeBytes { raw in
                    let values = raw.bindMemory(to: Float.self)
                    for index in 0..<256 {
                        let entry = Int(PlanarTransfer.rgbByte(values[index * 16]))
                        for channel in 0..<3 { table[4 * index + channel] = composed[4 * entry + channel] }
                    }
                }
            } else {
                transfer = PlanarTransfer(table: floats, level: transferLevel, width: transferWidth,
                    inverted: (value["transferInverted"] as? NSNumber)?.boolValue == true)
            }
        }
        var slab: PlanarSlab?
        if hostBytes == nil, let mode = value["slabMode"] {
            guard let stackMode = (mode as? NSNumber)?.intValue, let projection = PlanarSlab.projection(stackMode: stackMode),
                  let others = value["slabSlices"] as? Data, let count = (value["slabCount"] as? NSNumber)?.intValue,
                  !isColor, count >= 2, count <= 2048, others.count == (count - 1) * data.count
            else { throw fail() }
            slab = PlanarSlab(projection: projection, others: others, count: count)
        }
        var convolution: PlanarConvolution?
        if hostBytes == nil, let size = value["convolutionSize"] {
            guard let n = (size as? NSNumber)?.intValue, let kernel = value["convolutionKernel"] as? Data,
                  kernel.count == 25 * MemoryLayout<Float>.size,
                  let normalization = (value["convolutionNormalization"] as? NSNumber)?.floatValue,
                  let made = PlanarConvolution(size: n, kernel: kernel.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) },
                                               normalization: normalization, colour: isColor)
            else { throw fail() }
            convolution = made
        }
        pixels = data; clut = table; identifier = id; self.transfer = transfer; self.slab = slab; self.convolution = convolution
        self.hostBytes = hostBytes
        self.colourTable = colourTable
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
        // The table's bytes are the window's output; the fragment reads them the
        // way the original's scalar CLUT program reads host-prepared bytes, with
        // level 0.5 and width 1, polarity already in the bytes.
        // Host bytes are drawn as the host's are: scalar through the level 0.5,
        // width 1 read of the table path; colour as the fixed-function texture
        // draws them, the interpolated bytes themselves (window.z 2, #660).
        // Polarity, mask and table are already in the bytes.
        if hostBytes != nil {
            window = isColor ? SIMD4(127.5, 255, 2, nearest ? 1 : 0) : SIMD4(0.5, 1, 0, nearest ? 1 : 0)
        } else {
            window = transfer == nil ? SIMD4(level.floatValue, ww.floatValue, isColor ? 1 : 0, nearest ? 1 : 0)
                                     : SIMD4(0.5, 1, 0, nearest ? 1 : 0)
        }
        // The host enlarges a scalar image's samples or bytes, and a colour
        // image's bytes; never with nearest sampling, which turns it off.
        guard softwareScale == 1 || (window.w == 0 && (window.z == 0 || hostBytes != nil)) else { throw fail() }
        guard [mapping.x,mapping.y,mapping.z,mapping.w,geometry.x,geometry.y,geometry.z,geometry.w,
               window.x-window.y*0.5].allSatisfy({ $0.isFinite }) else { throw fail() }
        if window.z != 0 {
            let span = ((window.x + window.y*0.5) - (window.x - window.y*0.5)).rounded(.towardZero)
            guard span.isFinite, abs(span) >= 1 else { throw fail() }
        }
        if let fused = value["fusion"] {
            // A scalar series, as the host's CLUT program draws it; a colour
            // one, or one carrying a fusion of its own, is not drawn here.
            guard let layer = fused as? NSDictionary, let frame = try? PlanarFrame(layer),
                  frame.fusion.isEmpty, frame.window.z == 0 else { throw fail() }
            fusion = [frame]
        }
    }

    /// This frame without the series fused over it: what its own textures hold.
    var unfused: PlanarFrame {
        var frame = self
        frame.fusion = []
        return frame
    }

    /// Match the host's optional vImage scalar enlargement, retaining float
    /// intensities through both resampling stages. CLUT and windowing follow
    /// the final GPU sample; the source used by ROI measurements stays intact.
    /// `samples` is what the host enlarges: the image, or its thick slab.
    func texturePixels(_ samples: Data? = nil) throws -> Data {
        let samples = samples ?? pixels
        if softwareScale == 1 { return samples }
        let w = width * softwareScale, h = height * softwareScale
        var result = Data(count: w * h * 4)
        let status = result.withUnsafeMutableBytes { destination in
            samples.withUnsafeBytes { source in
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

    /// The pixels both backends upload, and their format: the host's float
    /// samples, its ARGB bytes, or, with an opacity table, the display bytes
    /// `PlanarTransferPass` made from the float samples. An enlarged table image
    /// is enlarged after the table, from those bytes, as the host enlarges its
    /// 8-bit buffer (`vImageScale_Planar8`, the same flags). A thick slab is
    /// reduced first: the host windows, tables and enlarges the reduction. A
    /// convolution filter follows the slab, as `-[DCMPix computefImage]` runs it.
    /// Colour host bytes are tabled, then enlarged, in the order and with the
    /// vImage calls of `loadTextureIn:` (#660).
    func uploadPixels(device: MTLDevice) throws -> (pixels: Data, format: MTLPixelFormat, bytesPerPixel: Int) {
        if let hostBytes {
            if window.z != 0 {
                var bytes = hostBytes
                if let colourTable { bytes = try PlanarFrame.lookUp(bytes: bytes, tables: colourTable, width: width, height: height) }
                return (try PlanarFrame.enlargeARGB(bytes: bytes, width: width, height: height, scale: softwareScale), .rgba8Unorm, 4)
            }
            return (try PlanarFrame.enlarge(bytes: hostBytes, width: width, height: height, scale: softwareScale), .r8Unorm, 1)
        }
        var samples = pixels
        if let slab {
            samples = try PlanarSlabProjection.shared(for: device).project(slab, current: pixels, width: width, height: height)
        }
        if let convolution {
            samples = try PlanarConvolutionPass.shared(for: device).apply(convolution, to: samples, width: width, height: height)
        }
        guard let transfer else { return (try texturePixels(samples), window.z == 0 ? .r32Float : .rgba8Unorm, 4) }
        let bytes = try PlanarTransferPass.shared(for: device).apply(transfer, to: samples, count: width * height)
        return (try PlanarFrame.enlarge(bytes: bytes, width: width, height: height, scale: softwareScale), .r8Unorm, 1)
    }

    /// The host's table over a colour image's ARGB bytes,
    /// `vImageTableLookUp_ARGB8888` with the alpha, red, green and blue tables.
    static func lookUp(bytes: Data, tables: Data, width: Int, height: Int) throws -> Data {
        guard bytes.count == width * height * 4, tables.count == 1024 else { throw PlanarMetalRenderer.failure() }
        var result = Data(count: bytes.count)
        // vImage reads the source through a mutable pointer it never writes:
        // no copy of the bytes to get one.
        let status = result.withUnsafeMutableBytes { destination in
            bytes.withUnsafeBytes { source in
                tables.withUnsafeBytes { table in
                    var from = vImage_Buffer(data: UnsafeMutableRawPointer(mutating: source.baseAddress!), height: vImagePixelCount(height),
                        width: vImagePixelCount(width), rowBytes: width * 4)
                    var to = vImage_Buffer(data: destination.baseAddress!, height: vImagePixelCount(height),
                        width: vImagePixelCount(width), rowBytes: width * 4)
                    let entries = table.bindMemory(to: Pixel_8.self)
                    return vImageTableLookUp_ARGB8888(&from, &to, entries.baseAddress!, entries.baseAddress! + 256,
                                                      entries.baseAddress! + 512, entries.baseAddress! + 768, vImage_Flags(kvImageNoFlags))
                }
            }
        }
        guard status == kvImageNoError else { throw PlanarMetalRenderer.failure() }
        return result
    }

    /// The host's enlargement of a colour image's bytes, `vImageScale_ARGB8888`
    /// with no flags; the bytes as they are at 1x.
    static func enlargeARGB(bytes: Data, width: Int, height: Int, scale: Int) throws -> Data {
        guard scale > 1 else { return bytes }
        let w = width * scale, h = height * scale
        var result = Data(count: w * h * 4)
        let status = result.withUnsafeMutableBytes { destination in
            bytes.withUnsafeBytes { source in
                var from = vImage_Buffer(data: UnsafeMutableRawPointer(mutating: source.baseAddress!), height: vImagePixelCount(height),
                    width: vImagePixelCount(width), rowBytes: width * 4)
                var to = vImage_Buffer(data: destination.baseAddress!, height: vImagePixelCount(h),
                    width: vImagePixelCount(w), rowBytes: w * 4)
                return vImageScale_ARGB8888(&from, &to, nil, vImage_Flags(kvImageNoFlags))
            }
        }
        guard status == kvImageNoError else { throw PlanarMetalRenderer.failure() }
        return result
    }

    /// The host's enlargement of an 8-bit image, `vImageScale_Planar8` with no
    /// flags; the bytes as they are at 1x.
    static func enlarge(bytes: Data, width: Int, height: Int, scale: Int) throws -> Data {
        guard scale > 1 else { return bytes }
        let w = width * scale, h = height * scale
        var input = bytes, result = Data(count: w * h)
        let status = result.withUnsafeMutableBytes { destination in
            input.withUnsafeMutableBytes { source in
                var from = vImage_Buffer(data: source.baseAddress!, height: vImagePixelCount(height),
                    width: vImagePixelCount(width), rowBytes: width)
                var to = vImage_Buffer(data: destination.baseAddress!, height: vImagePixelCount(h),
                    width: vImagePixelCount(w), rowBytes: w)
                return vImageScale_Planar8(&from, &to, nil, vImage_Flags(kvImageNoFlags))
            }
        }
        guard status == kvImageNoError else { throw PlanarMetalRenderer.failure() }
        return result
    }
}

/// A convolution filter from the 2D viewer's menu (#661), where the host runs it:
/// on the source values, after a thick slab and before the window, the opacity
/// table and any enlargement (`-[DCMPix computefImage]`; for colour, on the ARGB
/// bytes before the window table). The host calls vImage, with edge extension
/// and the kernel applied as a correlation, not flipped:
///
/// - scalar, `vImageConvolve_PlanarF`, the kernel divided by the normalisation
///   in float (as it is when that is zero); DCMPix then writes the source's first
///   value over the whole first row. vImage sums in an order of its own, so the
///   pass is not bit for bit: it sums each window row by row, one rounding per
///   product and per sum, which stays within the float summation bound of
///   vImage's result (`tests/test-planar-convolution.py`);
/// - colour, `vImageConvolve_ARGB8888`, the kernel in integers and the
///   normalisation as divisor, the first byte left alone: each other byte is
///   clamp((Σ + divisor / 2) / divisor) with C division, a divisor of zero taken
///   as one, bit for bit.
struct PlanarConvolution: Equatable {
    let size: Int
    let colour: Bool
    /// The scalar weights, `(float) kernel[i] / (float) normalization` as the host computes them.
    let weights: [Float]
    /// The colour kernel and divisor, converted as the host converts them for vImage.
    let integers: [Int32]
    let divisor: Int32

    init?(size: Int, kernel: [Float], normalization: Float, colour: Bool) {
        guard size >= 1, size <= 5, size % 2 == 1, kernel.count >= size * size, normalization.isFinite,
              abs(normalization) < 2_147_483_647, kernel.prefix(size * size).allSatisfy({ $0.isFinite && abs($0) < 32768 })
        else { return nil }
        self.size = size
        self.colour = colour
        let used = Array(kernel.prefix(size * size))
        weights = used.map { normalization != 0 ? $0 / normalization : $0 }
        integers = used.map { Int32($0.rounded(.towardZero)) }
        divisor = Int32(normalization.rounded(.towardZero))
    }
}

/// Runs `PlanarConvolution` on the GPU, compiled with safe math. One compiled
/// pass per device, shared by both backends and the comparison window.
final class PlanarConvolutionPass {
    static let shader = #"""
    #include <metal_stdlib>
    using namespace metal;
    struct ConvolutionParams { uint width; uint height; uint size; int divisor; };
    // vImageConvolve_PlanarF with edge extension: a correlation over the clamped
    // neighbourhood, summed row by row. DCMPix then writes the source's first
    // value over the first row.
    kernel void planarConvolveScalar(device const float *source [[buffer(0)]], constant float *weights [[buffer(1)]],
        device float *destination [[buffer(2)]], constant ConvolutionParams &p [[buffer(3)]],
        uint2 id [[thread_position_in_grid]]) {
        if (id.x >= p.width || id.y >= p.height) return;
        int n = int(p.size), radius = n / 2;
        float sum = 0.0f;
        for (int j = 0; j < n; ++j) {
            uint y = uint(clamp(int(id.y) + j - radius, 0, int(p.height) - 1));
            for (int i = 0; i < n; ++i) {
                uint x = uint(clamp(int(id.x) + i - radius, 0, int(p.width) - 1));
                sum = sum + source[y * p.width + x] * weights[j * n + i];
            }
        }
        destination[id.y * p.width + id.x] = id.y == 0 ? source[0] : sum;
    }
    // vImageConvolve_ARGB8888 with edge extension and the first byte left alone:
    // integer sums, (sum + divisor / 2) / divisor with C division, clamped.
    kernel void planarConvolveARGB(device const uchar4 *source [[buffer(0)]], constant int *weights [[buffer(1)]],
        device uchar4 *destination [[buffer(2)]], constant ConvolutionParams &p [[buffer(3)]],
        uint2 id [[thread_position_in_grid]]) {
        if (id.x >= p.width || id.y >= p.height) return;
        int n = int(p.size), radius = n / 2;
        int3 sum = int3(0);
        for (int j = 0; j < n; ++j) {
            uint y = uint(clamp(int(id.y) + j - radius, 0, int(p.height) - 1));
            for (int i = 0; i < n; ++i) {
                uint x = uint(clamp(int(id.x) + i - radius, 0, int(p.width) - 1));
                sum += int3(source[y * p.width + x].yzw) * weights[j * n + i];
            }
        }
        int divisor = p.divisor == 0 ? 1 : p.divisor;
        int3 value = clamp((sum + divisor / 2) / divisor, 0, 255);
        uchar4 kept = source[id.y * p.width + id.x];
        destination[id.y * p.width + id.x] = uchar4(kept.x, uchar(value.x), uchar(value.y), uchar(value.z));
    }
    """#

    private static let lock = NSLock()
    private static var passes: [UInt64: PlanarConvolutionPass] = [:]

    /// A compilation that fails is not remembered.
    static func shared(for device: MTLDevice) throws -> PlanarConvolutionPass {
        try lock.withLock {
            if let existing = passes[device.registryID] { return existing }
            let created = try PlanarConvolutionPass(device: device)
            passes[device.registryID] = created
            return created
        }
    }

    let device: MTLDevice
    private let queue: MTLCommandQueue
    private let scalar: MTLComputePipelineState
    private let argb: MTLComputePipelineState

    private init(device: MTLDevice) throws {
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw PlanarMetalRenderer.failure() }
        self.queue = queue
        let options = MTLCompileOptions()
        options.mathMode = .safe
        let library = try device.makeLibrary(source: Self.shader, options: options)
        guard let scalarFunction = library.makeFunction(name: "planarConvolveScalar"),
              let argbFunction = library.makeFunction(name: "planarConvolveARGB") else { throw PlanarMetalRenderer.failure() }
        scalar = try device.makeComputePipelineState(function: scalarFunction)
        argb = try device.makeComputePipelineState(function: argbFunction)
    }

    /// The filtered image: floats for a scalar image, ARGB bytes for colour, the
    /// same size and layout as `samples`.
    func apply(_ convolution: PlanarConvolution, to samples: Data, width: Int, height: Int) throws -> Data {
        guard width > 0, height > 0, samples.count == width * height * 4,
              let source = samples.withUnsafeBytes({ device.makeBuffer(bytes: $0.baseAddress!, length: $0.count,
                                                                       options: .storageModeShared) }),
              let destination = device.makeBuffer(length: samples.count, options: .storageModeShared),
              let command = queue.makeCommandBuffer(),
              let encoder = command.makeComputeCommandEncoder() else { throw PlanarMetalRenderer.failure() }
        struct Params { var width: UInt32; var height: UInt32; var size: UInt32; var divisor: Int32 }
        var parameters = Params(width: UInt32(width), height: UInt32(height), size: UInt32(convolution.size),
                                divisor: convolution.divisor)
        let pipeline = convolution.colour ? argb : scalar
        encoder.setComputePipelineState(pipeline)
        encoder.setBuffer(source, offset: 0, index: 0)
        if convolution.colour {
            var weights = convolution.integers
            encoder.setBytes(&weights, length: weights.count * MemoryLayout<Int32>.stride, index: 1)
        } else {
            var weights = convolution.weights
            encoder.setBytes(&weights, length: weights.count * MemoryLayout<Float>.stride, index: 1)
        }
        encoder.setBuffer(destination, offset: 0, index: 2)
        encoder.setBytes(&parameters, length: MemoryLayout<Params>.stride, index: 3)
        let side = 16
        encoder.dispatchThreadgroups(MTLSize(width: (width + side - 1) / side, height: (height + side - 1) / side, depth: 1),
                                     threadsPerThreadgroup: MTLSize(width: side, height: side, depth: 1))
        encoder.endEncoding()
        command.commit()
        command.waitUntilCompleted()
        guard command.status == .completed else { throw command.error ?? PlanarMetalRenderer.failure() }
        return Data(bytes: destination.contents(), count: samples.count)
    }
}

/// The 2D thick slab on the MPR's reduction (#659): one volume of the slab's
/// slices, current first, and one plane through their voxel centres, so every
/// sample reads a stored value and the samples run in the host's order. The
/// kernel is compiled with safe math, which keeps the sum in that order and the
/// mean a multiplication by the correctly rounded reciprocal, as the host's
/// vDSP calls compute them. One per device, serialised: the engine holds the
/// volume it last uploaded, and the comparison window prepares frames off the
/// main thread.
final class PlanarSlabProjection {
    private static let lock = NSLock()
    private static var projections: [UInt64: PlanarSlabProjection] = [:]

    static func shared(for device: MTLDevice) throws -> PlanarSlabProjection {
        try lock.withLock {
            if let existing = projections[device.registryID] { return existing }
            let created = PlanarSlabProjection(engine: try MPRMetalReslicer(device: device, safeMath: true))
            projections[device.registryID] = created
            return created
        }
    }

    private let engine: MPRMetalReslicer
    private let lock = NSLock()
    private init(engine: MPRMetalReslicer) { self.engine = engine }

    /// The reduced image, `width * height` floats in the host's row order.
    func project(_ slab: PlanarSlab, current: Data, width: Int, height: Int) throws -> Data {
        guard slab.count >= 2, current.count == width * height * MemoryLayout<Float>.size,
              slab.others.count == (slab.count - 1) * current.count else { throw PlanarMetalRenderer.failure() }
        var voxels = Data(capacity: slab.count * current.count)
        voxels.append(current)
        voxels.append(slab.others)
        let volume = try ResliceVolume(width: width, height: height, depth: slab.count, voxels: voxels,
                                       voxelToWorld: matrix_identity_float4x4)
        // Index space is the world here: the plane's pixel (x, y) is voxel
        // (x, y), and a slab of count - 1 centred at (count - 1) / 2 samples
        // slices 0, 1, … count - 1, current slice first.
        let plane = try ReslicePlane(origin: SIMD3(0, 0, Float(slab.count - 1) * 0.5), rowStep: SIMD3(1, 0, 0),
                                     columnStep: SIMD3(0, 1, 0), width: width, height: height,
                                     thickness: Float(slab.count - 1), sampleStep: 1, projection: slab.projection,
                                     background: 0)
        guard plane.sampleCount == slab.count else { throw PlanarMetalRenderer.failure() }
        return try lock.withLock {
            defer { engine.release() }
            try engine.upload(volume)
            return try engine.reslice(plane)
        }
    }
}

/// Window, opacity table and polarity for a scalar image, on the GPU (#657).
///
/// One thread per source pixel writes the byte `applyNonLinearWLWWThread:`
/// writes, with the same float operations: the subtraction, then the product
/// with `ratio`, truncated and clamped to the 4096 entries. The 255 scale is a
/// float product here and a double one in the host; for a table value in
/// [0, 1] both truncate to the same byte, because a float product that rounds up
/// to an integer would need the exact one within half an ulp below it, which
/// 255 times a float in [0, 1) never is. Outside [0, 1] the host's conversion
/// has no defined result (it differs between its Debug and Release builds);
/// this pass clamps, as the host's RGB conversion does. Safe math keeps the
/// operations IEEE and NaN a value, as the host's arm64 conversion treats it:
/// index 0.
final class PlanarTransferPass {
    static let shader = #"""
    #include <metal_stdlib>
    using namespace metal;
    struct TransferParams { float from; float ratio; uint count; uint inverted; };
    kernel void planarTransfer(device const float *source [[buffer(0)]], device const float *table [[buffer(1)]],
        device uchar *destination [[buffer(2)]], constant TransferParams &p [[buffer(3)]],
        uint id [[thread_position_in_grid]]) {
        if (id >= p.count) return;
        float scaled = p.ratio * (source[id] - p.from);
        int index = isnan(scaled) ? 0 : int(clamp(scaled, 0.0f, 4095.0f));
        float product = 255.0f * table[index];
        uchar value = isnan(product) ? 0 : uchar(clamp(product, 0.0f, 255.0f));
        destination[id] = p.inverted != 0 ? 255 - value : value;
    }
    """#

    private static let lock = NSLock()
    private static var passes: [UInt64: PlanarTransferPass] = [:]

    /// One compiled pass per device, shared by both backends and the comparison
    /// window. A compilation that fails is not remembered.
    static func shared(for device: MTLDevice) throws -> PlanarTransferPass {
        try lock.withLock {
            if let existing = passes[device.registryID] { return existing }
            let created = try PlanarTransferPass(device: device)
            passes[device.registryID] = created
            return created
        }
    }

    let device: MTLDevice
    private let queue: MTLCommandQueue
    private let pipeline: MTLComputePipelineState

    private init(device: MTLDevice) throws {
        self.device = device
        guard let queue = device.makeCommandQueue() else { throw PlanarMetalRenderer.failure() }
        self.queue = queue
        let options = MTLCompileOptions()
        options.mathMode = .safe
        let library = try device.makeLibrary(source: Self.shader, options: options)
        guard let function = library.makeFunction(name: "planarTransfer") else { throw PlanarMetalRenderer.failure() }
        pipeline = try device.makeComputePipelineState(function: function)
    }

    /// The display bytes of `count` float samples, in source order.
    func apply(_ transfer: PlanarTransfer, to samples: Data, count: Int) throws -> Data {
        guard count > 0, samples.count == count * MemoryLayout<Float>.size,
              transfer.table.count == 4096 * MemoryLayout<Float>.size,
              let source = samples.withUnsafeBytes({ device.makeBuffer(bytes: $0.baseAddress!, length: $0.count,
                                                                       options: .storageModeShared) }),
              let table = transfer.table.withUnsafeBytes({ device.makeBuffer(bytes: $0.baseAddress!, length: $0.count,
                                                                             options: .storageModeShared) }),
              let destination = device.makeBuffer(length: count, options: .storageModeShared),
              let command = queue.makeCommandBuffer(),
              let encoder = command.makeComputeCommandEncoder() else { throw PlanarMetalRenderer.failure() }
        struct Params { var from: Float; var ratio: Float; var count: UInt32; var inverted: UInt32 }
        var parameters = Params(from: transfer.from, ratio: transfer.ratio, count: UInt32(count),
                                inverted: transfer.inverted ? 1 : 0)
        encoder.setComputePipelineState(pipeline)
        encoder.setBuffer(source, offset: 0, index: 0)
        encoder.setBuffer(table, offset: 0, index: 1)
        encoder.setBuffer(destination, offset: 0, index: 2)
        encoder.setBytes(&parameters, length: MemoryLayout<Params>.stride, index: 3)
        let group = min(pipeline.maxTotalThreadsPerThreadgroup, 256)
        encoder.dispatchThreadgroups(MTLSize(width: (count + group - 1) / group, height: 1, depth: 1),
                                     threadsPerThreadgroup: MTLSize(width: group, height: 1, depth: 1))
        encoder.endEncoding()
        command.commit()
        command.waitUntilCompleted()
        guard command.status == .completed else { throw command.error ?? PlanarMetalRenderer.failure() }
        return Data(bytes: destination.contents(), count: count)
    }
}

/// The textures of a frame and of the series fused over it (#658), which both
/// backends draw. A layer that did not change keeps the textures it has, so
/// moving the fusion factor, which changes only the fused CLUT's alpha column,
/// uploads the fused series again and never the image, and no pipeline is
/// rebuilt. Textures are never written after they are made, so one an earlier
/// submission is still reading can be kept.
struct PlanarTextures {
    let frame: PlanarFrame
    let image: MTLTexture, clut: MTLTexture
    let fused: (image: MTLTexture, clut: MTLTexture)?

    init(_ frame: PlanarFrame, reusing previous: PlanarTextures?, device: MTLDevice) throws {
        let own = frame.unfused
        if let previous, previous.frame.unfused == own {
            (image, clut) = (previous.image, previous.clut)
        } else {
            (image, clut) = try PlanarMetalRenderer.makeTextures(for: own, device: device)
        }
        if let layer = frame.fusion.first {
            if let previous, let kept = previous.fused, previous.frame.fusion.first == layer {
                fused = kept
            } else {
                fused = try PlanarMetalRenderer.makeTextures(for: layer, device: device)
            }
        } else {
            fused = nil
        }
        self.frame = frame
    }
}

/// The scalar sampling -> window -> CLUT order follows the donor fork's planar
/// fragment shader; provenance in NOTICE. Host decoding, geometry and sessions
/// are deliberately not imported from it.
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
    // The colour an image contributes at a target position, alpha from the
    // CLUT's fourth column; `inside` is false off the view or the image.
    static float4 planarShade(float2 position, constant Params &p, texture2d<float> image,
        texture2d<float, access::read> clut, thread bool &inside) {
        inside=false;
        float scale=min(p.output.x/p.geometry.z,p.output.y/p.geometry.w);
        float2 size=p.geometry.zw*scale;
        float2 point=(position-(p.output.xy-size)*0.5)/size;
        if(any(point<0.0)||any(point>=1.0))return float4(0);
        float2 pixel=p.mapping.xy+point.x*p.mapping.zw+point.y*p.geometry.xy;
        float2 dimensions=float2(image.get_width(),image.get_height())/p.output.w;
        if(any(pixel<0.0)||any(pixel>=dimensions))return float4(0);
        inside=true;
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
        // The host's colour bytes, tabled and windowed already: the interpolated
        // bytes are the colour, as the fixed-function texture draws them (#660).
        if(p.window.z > 1.5) return float4(sampled.gba,1);
        if(p.window.z != 0) {
            // DCMPix's RGB conversion table truncates both its window span
            // (long diff = max-min) and each index before the discrete CLUT.
            float span=trunc((p.window.x+p.window.y*0.5)-minimum);
            float3 rgb=clamp((sampled.gba*255.0-minimum)*255.0/span,0.0,255.0);
            uint3 index=uint3(rgb);
            return float4(clut.read(uint2(index.r,0)).r,clut.read(uint2(index.g,0)).g,
                          clut.read(uint2(index.b,0)).b,1);
        }
        if(!isfinite(sampled.r))return float4(0,0,0,0);
        float normalized=clamp((sampled.r-minimum)/p.window.y,0.0,1.0);
        return clut.read(uint2(uint(normalized*255.0+0.5),0));
    }
    fragment float4 planarFragment(Vertex in [[stage_in]], constant Params &p [[buffer(0)]],
        texture2d<float> image [[texture(0)]], texture2d<float, access::read> clut [[texture(1)]]) {
        bool inside;
        float4 colour=planarShade(in.position.xy,p,image,clut,inside);
        return inside?float4(colour.rgb,1):float4(p.output.zzz,1);
    }
    // The fused series (#658), drawn after the image with the host's
    // GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA blend, and only over its own image:
    // elsewhere the image shows, as it does where the host's quad ends.
    fragment float4 planarFusionFragment(Vertex in [[stage_in]], constant Params &p [[buffer(0)]],
        texture2d<float> image [[texture(0)]], texture2d<float, access::read> clut [[texture(1)]]) {
        bool inside;
        float4 colour=planarShade(in.position.xy,p,image,clut,inside);
        if(!inside)discard_fragment();
        return colour;
    }
    """#
    let device: MTLDevice
    let queue: MTLCommandQueue
    let pipeline: MTLRenderPipelineState
    let fusionPipeline: MTLRenderPipelineState
    private var textures: PlanarTextures?
    var image: MTLTexture? { textures?.image }

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
        descriptor.fragmentFunction = library.makeFunction(name: "planarFusionFragment")
        let blend = descriptor.colorAttachments[0]!
        blend.isBlendingEnabled = true
        blend.rgbBlendOperation = .add; blend.alphaBlendOperation = .add
        blend.sourceRGBBlendFactor = .sourceAlpha; blend.destinationRGBBlendFactor = .oneMinusSourceAlpha
        blend.sourceAlphaBlendFactor = .sourceAlpha; blend.destinationAlphaBlendFactor = .oneMinusSourceAlpha
        fusionPipeline = try device.makeRenderPipelineState(descriptor: descriptor)
    }

    static func failure() -> NSError {
        NSError(domain: "HorosPlanar", code: 2, userInfo: [NSLocalizedDescriptionKey:
            NSLocalizedString("Metal comparison is unavailable. Use the original viewer.", comment: "")])
    }

    func update(_ frame: PlanarFrame) throws {
        textures = try PlanarTextures(frame, reusing: textures, device: device)
    }

    /// The fragment parameters of one layer drawn into a target.
    static func parameters(for frame: PlanarFrame, width: Int, height: Int) -> [SIMD4<Float>] {
        [frame.mapping, frame.geometry, frame.window,
         SIMD4<Float>(Float(width), Float(height), frame.background, Float(frame.softwareScale))]
    }

    /// The image and CLUT textures of a frame. Both backends upload through
    /// here, so the pilot samples exactly what this renderer samples.
    static func makeTextures(for frame: PlanarFrame, device: MTLDevice) throws -> (image: MTLTexture, clut: MTLTexture) {
        let (pixels, format, bytesPerPixel) = try frame.uploadPixels(device: device)
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: format,
            width: frame.width * frame.softwareScale, height: frame.height * frame.softwareScale, mipmapped: false)
        descriptor.storageMode = .shared; descriptor.usage = .shaderRead
        let tableDescriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .rgba8Unorm,
            width: 256, height: 1, mipmapped: false)
        tableDescriptor.storageMode = .shared; tableDescriptor.usage = .shaderRead
        guard let image = device.makeTexture(descriptor: descriptor),
              let table = device.makeTexture(descriptor: tableDescriptor),
              pixels.count == image.width * image.height * bytesPerPixel else { throw Self.failure() }
        pixels.withUnsafeBytes { bytes in
            image.replace(region: MTLRegionMake2D(0,0,image.width,image.height), mipmapLevel: 0,
                          withBytes: bytes.baseAddress!, bytesPerRow: image.width*bytesPerPixel)
        }
        frame.clut.withUnsafeBytes { bytes in
            table.replace(region: MTLRegionMake2D(0,0,256,1), mipmapLevel: 0,
                          withBytes: bytes.baseAddress!, bytesPerRow: 1024)
        }
        return (image, table)
    }

    /// All retained resources belong to this frame; a command buffer retains
    /// its own references until completion, including during cancellation.
    func clear() { textures = nil }

    /// The image, then the fused series over it, in the host's order.
    func encode(into target: MTLTexture, command: MTLCommandBuffer) throws {
        guard let textures else { throw Self.failure() }
        let pass = MTLRenderPassDescriptor()
        pass.colorAttachments[0].texture = target
        pass.colorAttachments[0].loadAction = .clear; pass.colorAttachments[0].storeAction = .store
        pass.colorAttachments[0].clearColor = MTLClearColorMake(0,0,0,1)
        guard let encoder = command.makeRenderCommandEncoder(descriptor: pass) else { throw Self.failure() }
        var parameters = Self.parameters(for: textures.frame, width: target.width, height: target.height)
        encoder.setRenderPipelineState(pipeline)
        encoder.setFragmentBytes(&parameters, length: 4*MemoryLayout<SIMD4<Float>>.stride, index: 0)
        encoder.setFragmentTexture(textures.image, index: 0); encoder.setFragmentTexture(textures.clut, index: 1)
        encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
        if let fused = textures.fused, let layer = textures.frame.fusion.first {
            var fusedParameters = Self.parameters(for: layer, width: target.width, height: target.height)
            encoder.setRenderPipelineState(fusionPipeline)
            encoder.setFragmentBytes(&fusedParameters, length: 4*MemoryLayout<SIMD4<Float>>.stride, index: 0)
            encoder.setFragmentTexture(fused.image, index: 0); encoder.setFragmentTexture(fused.clut, index: 1)
            encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
        }
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
