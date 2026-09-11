import CryptoKit
import Foundation

/// One coplanar layer of a PET/CT fusion, in the same units DCMPix uses.
///
/// `samples` are native pixel values, row-major, one `Float` per pixel.
/// `spacing` is pixelSpacingX then pixelSpacingY — the distance between
/// columns first and between rows second, matching DCMPix rather than the
/// DICOM Pixel Spacing tag, which writes those two the other way round.
/// `orientation` is the 6- or 9-vector DCMPix keeps: increasing column
/// index, then increasing row index, then the slice normal when present.
@objc(HorosOrthogonalFusionLayer)
public final class OrthogonalFusionLayer: NSObject {
    @objc public var samples = Data()
    @objc public var width = 0
    @objc public var height = 0
    @objc public var origin = [NSNumber]()
    @objc public var orientation = [NSNumber]()
    @objc public var spacing = [NSNumber]()
    @objc public var sliceLocation = 0.0
    @objc public var sliceThickness = 0.0
    @objc public var windowCenter = 0.0
    @objc public var windowWidth = 0.0
}

/// One fused RGB frame, with the geometry of the primary (CT) slice.
@objc(HorosOrthogonalFusionSlice)
public final class OrthogonalFusionSlice: NSObject {
    @objc public let pixelRGB: Data
    @objc public let width: Int
    @objc public let height: Int
    @objc public let origin: [NSNumber]
    @objc public let orientation: [NSNumber]
    @objc public let spacing: [NSNumber]
    @objc public let sliceLocation: Double
    @objc public let sliceThickness: Double
    @objc public let instanceNumber: Int
    @objc public let digest: String

    @objc public init(pixelRGB: Data, width: Int, height: Int, origin: [NSNumber],
                      orientation: [NSNumber], spacing: [NSNumber],
                      sliceLocation: Double, sliceThickness: Double,
                      instanceNumber: Int) {
        self.pixelRGB = pixelRGB
        self.width = width
        self.height = height
        self.origin = origin
        self.orientation = orientation
        self.spacing = spacing
        self.sliceLocation = sliceLocation
        self.sliceThickness = sliceThickness
        self.instanceNumber = instanceNumber
        self.digest = OrthogonalFusionSliceExport.digest(ofPixels: pixelRGB)
        super.init()
    }
}

/// Fuses PET onto CT in patient space, without reading the OpenGL front buffer.
///
/// The orthogonal PET/CT series export used to capture `GL_FRONT` after
/// `NSDisableScreenUpdates`, so every frame was the first image. Isolated
/// CT/PET already walk the 16-bit buffer in memory. This helper does the same
/// for the fused RGB: window each layer, sample the PET at the CT pixel's
/// patient coordinate, and keep the CT Image Position / Slice Location.
@objc(HorosOrthogonalFusionSliceExport)
public final class OrthogonalFusionSliceExport: NSObject {
    /// 0-based half-open indices, after the exporter subtracts 1 from the
    /// 1-based From/To fields. A reversed range is ordered; a non-positive
    /// interval becomes 1 so the loop cannot run forever.
    @objc(sliceIndicesFrom:to:interval:)
    public static func sliceIndices(from: Int, to: Int, interval: Int) -> [NSNumber] {
        var start = from
        var end = to
        if end < start { swap(&start, &end) }
        let step = interval > 0 ? interval : 1
        var indices: [NSNumber] = []
        var i = start
        while i < end {
            indices.append(NSNumber(value: i))
            i += step
        }
        return indices
    }

    /// WL/WW as Horos uses them: the window runs from center − width/2.
    @objc(windowedByteForValue:windowCenter:windowWidth:)
    public static func windowedByte(value: Double, windowCenter: Double, windowWidth: Double) -> UInt8 {
        guard windowWidth.isFinite, windowWidth > 0, value.isFinite, windowCenter.isFinite else { return 0 }
        let low = windowCenter - windowWidth / 2
        let scaled = (value - low) / windowWidth * 255
        return UInt8(max(0, min(255, scaled.rounded())))
    }

    @objc(digestOfPixels:)
    public static func digest(ofPixels pixels: Data) -> String {
        SHA256.hash(data: pixels).map { String(format: "%02x", $0) }.joined()
    }

    /// Linear fusion. Horos' blending slider is −256…256; 0 is a 50 % mix.
    @objc(sliceFromPrimary:secondary:lut:blendingFactor:instanceNumber:)
    public static func slice(fromPrimary primary: OrthogonalFusionLayer,
                              secondary: OrthogonalFusionLayer?,
                              lut: Data?,
                              blendingFactor: Double,
                              instanceNumber: Int) -> OrthogonalFusionSlice? {
        let count = primary.width * primary.height
        guard primary.width > 0, primary.height > 0,
              let primarySamples = floats(primary.samples, count: count),
              primary.origin.count == 3, primary.spacing.count == 2
        else { return nil }

        let spacingX = primary.spacing[0].doubleValue
        let spacingY = primary.spacing[1].doubleValue
        guard spacingX.isFinite, spacingY.isFinite, spacingX != 0, spacingY != 0 else { return nil }

        let origin = primary.origin.map { $0.doubleValue }
        let orientation = primary.orientation.map { $0.doubleValue }
        guard origin.allSatisfy({ $0.isFinite }) else { return nil }

        var secondarySamples: [Float] = []
        var secondaryOrigin: [Double] = []
        var secondaryOrientation: [Double] = []
        var secondarySpacingX = 0.0
        var secondarySpacingY = 0.0
        var secondaryWidth = 0
        var secondaryHeight = 0
        var secondaryWindowCenter = 0.0
        var secondaryWindowWidth = 0.0
        if let secondary {
            let n = secondary.width * secondary.height
            guard secondary.width > 0, secondary.height > 0,
                  let samples = floats(secondary.samples, count: n),
                  secondary.origin.count == 3, secondary.spacing.count == 2
            else { return nil }
            secondarySamples = samples
            secondaryOrigin = secondary.origin.map { $0.doubleValue }
            secondaryOrientation = secondary.orientation.map { $0.doubleValue }
            secondarySpacingX = secondary.spacing[0].doubleValue
            secondarySpacingY = secondary.spacing[1].doubleValue
            secondaryWidth = secondary.width
            secondaryHeight = secondary.height
            secondaryWindowCenter = secondary.windowCenter
            secondaryWindowWidth = secondary.windowWidth
            guard secondarySpacingX != 0, secondarySpacingY != 0,
                  secondaryOrigin.allSatisfy({ $0.isFinite }) else { return nil }
        }

        let opacity = max(0, min(1, (blendingFactor + 256) / 512))
        let table: [UInt8]? = {
            guard let lut, lut.count == 768 else { return nil }
            return [UInt8](lut)
        }()

        var pixels = [UInt8](repeating: 0, count: count * 3)
        for row in 0..<primary.height {
            for column in 0..<primary.width {
                let ct = windowedByte(value: Double(primarySamples[row * primary.width + column]),
                                       windowCenter: primary.windowCenter,
                                       windowWidth: primary.windowWidth)
                var pet: UInt8 = 0
                if !secondarySamples.isEmpty {
                    let patient = Self.patient(origin: origin, orientation: orientation,
                                                 spacingX: spacingX, spacingY: spacingY,
                                                 column: column, row: row)
                    if let sample = Self.sample(secondarySamples,
                                                   width: secondaryWidth, height: secondaryHeight,
                                                   origin: secondaryOrigin,
                                                   orientation: secondaryOrientation,
                                                   spacingX: secondarySpacingX,
                                                   spacingY: secondarySpacingY,
                                                   patient: patient) {
                        pet = windowedByte(value: Double(sample),
                                            windowCenter: secondaryWindowCenter,
                                            windowWidth: secondaryWindowWidth)
                    }
                }
                let overlay = lutRGB(from: pet, lut: table)
                let i = (row * primary.width + column) * 3
                pixels[i] = mix(ct, overlay.0, opacity)
                pixels[i + 1] = mix(ct, overlay.1, opacity)
                pixels[i + 2] = mix(ct, overlay.2, opacity)
            }
        }

        return OrthogonalFusionSlice(pixelRGB: Data(pixels),
                                       width: primary.width,
                                       height: primary.height,
                                       origin: primary.origin,
                                       orientation: primary.orientation,
                                       spacing: primary.spacing,
                                       sliceLocation: primary.sliceLocation,
                                       sliceThickness: primary.sliceThickness,
                                       instanceNumber: instanceNumber)
    }

    private static func floats(_ data: Data, count: Int) -> [Float]? {
        let bytes = count * MemoryLayout<Float>.size
        guard count > 0, data.count >= bytes else { return nil }
        return data.prefix(bytes).withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
    }

    private static func patient(origin: [Double], orientation: [Double],
                                  spacingX: Double, spacingY: Double,
                                  column: Int, row: Int) -> (Double, Double, Double) {
        let col = direction(orientation, 0)
        let rowDir = direction(orientation, 3)
        return (
            origin[0] + Double(column) * col.0 * spacingX + Double(row) * rowDir.0 * spacingY,
            origin[1] + Double(column) * col.1 * spacingX + Double(row) * rowDir.1 * spacingY,
            origin[2] + Double(column) * col.2 * spacingX + Double(row) * rowDir.2 * spacingY
        )
    }

    private static func sample(_ samples: [Float], width: Int, height: Int,
                                origin: [Double], orientation: [Double],
                                spacingX: Double, spacingY: Double,
                                patient: (Double, Double, Double)) -> Float? {
        let colDir = direction(orientation, 0)
        let rowDir = direction(orientation, 3)
        let dx = patient.0 - origin[0]
        let dy = patient.1 - origin[1]
        let dz = patient.2 - origin[2]
        let column = (dx * colDir.0 + dy * colDir.1 + dz * colDir.2) / spacingX
        let row = (dx * rowDir.0 + dy * rowDir.1 + dz * rowDir.2) / spacingY
        let c = Int(column.rounded())
        let r = Int(row.rounded())
        guard c >= 0, r >= 0, c < width, r < height else { return nil }
        return samples[r * width + c]
    }

    private static func direction(_ orientation: [Double], _ start: Int) -> (Double, Double, Double) {
        if orientation.count >= start + 3 {
            return (orientation[start], orientation[start + 1], orientation[start + 2])
        }
        if start == 0 { return (1, 0, 0) }
        return (0, 1, 0)
    }

    private static func lutRGB(from gray: UInt8, lut: [UInt8]?) -> (UInt8, UInt8, UInt8) {
        if let lut {
            let i = Int(gray)
            return (lut[i * 3], lut[i * 3 + 1], lut[i * 3 + 2])
        }
        return (gray, gray, gray)
    }

    private static func mix(_ primary: UInt8, _ secondary: UInt8, _ opacity: Double) -> UInt8 {
        UInt8((Double(primary) * (1 - opacity) + Double(secondary) * opacity).rounded())
    }
}
