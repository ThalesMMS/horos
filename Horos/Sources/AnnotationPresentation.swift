import AppKit
import Darwin
import Foundation

/// Color-space identity, overlay contrast and measurement captions for the
/// annotation/ROI matrix. Overlay numbers are formatted from the same inputs
/// the viewer already computed; this type does not recompute HU, WL/WW or
/// ROI length.
@objc(HorosAnnotationPresentation)
public final class AnnotationPresentation: NSObject {
    public struct MatrixProfile {
        public let name: String
        public let colorSpace: NSColorSpace
    }

    private static let overlayCache: NSCache<NSArray, NSBitmapImageRep> = {
        let cache = NSCache<NSArray, NSBitmapImageRep>()
        cache.countLimit = 64
        return cache
    }()

    @objc(textureCacheTokenForWindow:)
    public static func textureCacheToken(for window: Any?) -> String {
        let space = (window as? NSWindow)?.colorSpace
            ?? NSScreen.main?.colorSpace
            ?? NSColorSpace.genericRGB
        return cacheToken(for: space)
    }

    @objc(cacheTokenForColorSpace:)
    public static func cacheToken(for space: NSColorSpace) -> String {
        if let data = space.iccProfileData, !data.isEmpty {
            var hash: UInt64 = 5381
            data.withUnsafeBytes { buffer in
                for byte in buffer {
                    hash = ((hash << 5) &+ hash) &+ UInt64(byte)
                }
            }
            return "icc:\(String(hash, radix: 16))"
        }
        return space.localizedName ?? "generic-rgb"
    }

    public static func matrixProfiles() -> [MatrixProfile] {
        var profiles: [MatrixProfile] = []
        func add(_ name: String, _ space: NSColorSpace?) {
            guard let space, space.colorSpaceModel == .rgb else { return }
            if profiles.contains(where: { $0.name == name }) { return }
            profiles.append(MatrixProfile(name: name, colorSpace: space))
        }
        add("sRGB", .sRGB)
        if let linear = CGColorSpace(name: CGColorSpace.linearSRGB) {
            add("linear", NSColorSpace(cgColorSpace: linear))
        }
        add("Color LCD", colorLCDSpace())
        for (index, screen) in NSScreen.screens.enumerated() {
            let label = screen.localizedName.isEmpty ? "\(index)" : screen.localizedName
            add("display:\(label)", screen.colorSpace)
        }
        return profiles
    }

    private static func colorLCDSpace() -> NSColorSpace {
        if let named = installedRGBSpace(matching: ["color lcd"]) { return named }
        if let lcd = installedRGBSpace(matching: [" lcd"]) { return lcd }
        // StringTexture rasterizes into NSCalibratedRGBColorSpace, Apple's
        // Generic RGB working space historically paired with Color LCD.
        return .genericRGB
    }

    private static func installedRGBSpace(matching names: [String]) -> NSColorSpace? {
        let directories = [
            "/System/Library/ColorSync/Profiles",
            "/Library/ColorSync/Profiles",
            "/Library/ColorSync/Profiles/Displays",
            NSHomeDirectory() + "/Library/ColorSync/Profiles"
        ]
        for directory in directories {
            guard let files = try? FileManager.default.contentsOfDirectory(atPath: directory) else { continue }
            for file in files {
                let lower = file.lowercased()
                guard lower.hasSuffix(".icc") || lower.hasSuffix(".icm") else { continue }
                let path = (directory as NSString).appendingPathComponent(file)
                guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
                      let space = NSColorSpace(iccProfileData: data),
                      space.colorSpaceModel == .rgb else { continue }
                let label = (space.localizedName ?? file).lowercased()
                if names.contains(where: { label.contains($0) || lower.contains($0) }) {
                    return space
                }
            }
        }
        for space in NSColorSpace.availableColorSpaces(with: .rgb) {
            let label = (space.localizedName ?? "").lowercased()
            if names.contains(where: { label.contains($0) }) { return space }
        }
        return nil
    }

    @objc(windowLevelWidthWithWl:ww:)
    public static func windowLevelWidth(wl: Double, ww: Double) -> String {
        if ww < 50 && (wl != Double(Int(wl)) || ww != Double(Int(ww))) {
            return String(format: "WL: %0.4f WW: %0.4f", wl, ww)
        }
        return String(format: "WL: %d WW: %d", Int(wl), Int(ww))
    }

    @objc(imageSizeWithWidth:height:)
    public static func imageSize(width: Int, height: Int) -> String {
        "Image size: \(width) x \(height)"
    }

    @objc(pixelValueWithX:y:hu:unit:)
    public static func pixelValue(x: Int, y: Int, hu: Double, unit: String) -> String {
        String(format: "X: %d px Y: %d px Value: %2.2f %@", x, y, hu, unit as NSString)
    }

    @objc(patientName:)
    public static func patientName(_ name: String) -> String { name }

    @objc(roiLengthWithCentimeters:)
    public static func roiLength(centimeters: Double) -> String {
        String(format: "Length: %.3f cm", centimeters)
    }

    public static func roiColor(red: UInt16, green: UInt16, blue: UInt16, opacity: CGFloat) -> NSColor {
        NSColor(calibratedRed: CGFloat(red) / 65535,
                green: CGFloat(green) / 65535,
                blue: CGFloat(blue) / 65535,
                alpha: opacity)
    }

    public static func convert(_ color: NSColor, to space: NSColorSpace) -> NSColor {
        color.usingColorSpace(space) ?? color
    }

    public static func rasterizeOverlay(_ text: String, font: NSFont, scale: CGFloat, whiteBackground: Bool) -> NSBitmapImageRep {
        let key: NSArray = [text, font.fontName, font.pointSize, scale, whiteBackground] as NSArray
        if let cached = overlayCache.object(forKey: key) { return cached }
        let glyphs = rasterizeGlyphs(text, font: font, scale: max(1, scale))
        let composed = composite(glyphs, whiteBackground: whiteBackground)
        overlayCache.setObject(composed, forKey: key)
        return composed
    }

    public static func glyphCoverage(in bitmap: NSBitmapImageRep) -> Double {
        let total = bitmap.pixelsWide * bitmap.pixelsHigh
        guard total > 0, let data = bitmap.bitmapData else { return 0 }
        var covered = 0
        for y in 0..<bitmap.pixelsHigh {
            let row = data + y * bitmap.bytesPerRow
            for x in 0..<bitmap.pixelsWide {
                if row[x * 4 + 3] > 16 { covered += 1 }
            }
        }
        return Double(covered) / Double(total)
    }

    public static func overlayContrast(_ text: String, font: NSFont, scale: CGFloat,
                                       whiteBackground: Bool, backgroundGray: Double,
                                       profile: NSColorSpace) -> Double {
        overlayContrast(in: rasterizeOverlay(text, font: font, scale: scale, whiteBackground: whiteBackground),
                         backgroundGray: backgroundGray, profile: profile)
    }

    public static func overlayContrast(in bitmap: NSBitmapImageRep, backgroundGray: Double,
                                        profile: NSColorSpace) -> Double {
        let gray = min(max(backgroundGray, 0), 1)
        let background = NSColor(calibratedWhite: CGFloat(gray), alpha: 1)
        guard let data = bitmap.bitmapData else { return 0 }
        var best = 1.0
        for y in 0..<bitmap.pixelsHigh {
            let row = data + y * bitmap.bytesPerRow
            for x in 0..<bitmap.pixelsWide {
                let a = Double(row[x * 4 + 3]) / 255
                guard a > 0.04 else { continue }
                let color = NSColor(calibratedRed: CGFloat(row[x * 4]) / 255,
                                     green: CGFloat(row[x * 4 + 1]) / 255,
                                     blue: CGFloat(row[x * 4 + 2]) / 255,
                                     alpha: 1)
                let ratio = contrastRatio(color, background, profile: profile)
                if ratio > best { best = ratio }
            }
        }
        return best
    }

    public static func contrastRatio(_ a: NSColor, _ b: NSColor, profile: NSColorSpace) -> Double {
        let lighter = max(relativeLuminance(a, profile: profile), relativeLuminance(b, profile: profile))
        let darker = min(relativeLuminance(a, profile: profile), relativeLuminance(b, profile: profile))
        return (lighter + 0.05) / (darker + 0.05)
    }

    private static func relativeLuminance(_ color: NSColor, profile: NSColorSpace) -> Double {
        let mapped = convert(color, to: profile)
        let srgb = mapped.usingColorSpace(.sRGB) ?? mapped
        func lin(_ component: CGFloat) -> Double {
            let x = max(0, min(1, Double(component)))
            return x <= 0.04045 ? x / 12.92 : pow((x + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * lin(srgb.redComponent) + 0.7152 * lin(srgb.greenComponent) + 0.0722 * lin(srgb.blueComponent)
    }

    private static func rasterizeGlyphs(_ text: String, font: NSFont, scale: CGFloat) -> NSBitmapImageRep {
        let attributes: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.white
        ]
        let size = (text as NSString).size(withAttributes: attributes)
        let logical = NSSize(width: max(1, ceil(size.width) + 8), height: max(1, ceil(size.height) + 4))
        let pixelsWide = max(1, Int((logical.width * scale).rounded()))
        let pixelsHigh = max(1, Int((logical.height * scale).rounded()))
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixelsWide, pixelsHigh: pixelsHigh,
                                       bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                       colorSpaceName: .calibratedRGB, bytesPerRow: 0, bitsPerPixel: 32)!
        bitmap.size = logical
        if let data = bitmap.bitmapData {
            memset(data, 0, bitmap.bytesPerRow * pixelsHigh)
        }
        NSGraphicsContext.saveGraphicsState()
        if let context = NSGraphicsContext(bitmapImageRep: bitmap) {
            NSGraphicsContext.current = context
            context.shouldAntialias = true
            (text as NSString).draw(at: NSPoint(x: 4, y: 2), withAttributes: attributes)
        }
        NSGraphicsContext.restoreGraphicsState()
        return bitmap
    }

    private static func composite(_ glyphs: NSBitmapImageRep, whiteBackground: Bool) -> NSBitmapImageRep {
        let width = glyphs.pixelsWide, height = glyphs.pixelsHigh
        let output = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                                        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                        colorSpaceName: .calibratedRGB, bytesPerRow: 0, bitsPerPixel: 32)!
        output.size = glyphs.size
        guard let src = glyphs.bitmapData, let dst = output.bitmapData else { return glyphs }
        memset(dst, 0, output.bytesPerRow * height)
        let shadow: CGFloat = whiteBackground ? 1 : 0
        let text: CGFloat = whiteBackground ? 0 : 1
        func coverage(_ x: Int, _ y: Int) -> CGFloat {
            guard x >= 0, y >= 0, x < width, y < height else { return 0 }
            return CGFloat(src[y * glyphs.bytesPerRow + x * 4 + 3]) / 255
        }
        func blend(x: Int, y: Int, tone: CGFloat, alpha: CGFloat) {
            guard alpha > 0, x >= 0, y >= 0, x < width, y < height else { return }
            let i = y * output.bytesPerRow + x * 4
            let dstA = CGFloat(dst[i + 3]) / 255
            let srcA = min(alpha, 1)
            let outA = srcA + dstA * (1 - srcA)
            guard outA > 0 else { return }
            for c in 0..<3 {
                let srcC = tone * srcA
                let dstC = CGFloat(dst[i + c]) / 255
                dst[i + c] = UInt8(min(255, ((srcC + dstC * (1 - srcA)) / outA) * 255).rounded())
            }
            dst[i + 3] = UInt8(min(255, outA * 255).rounded())
        }
        for y in 0..<height {
            for x in 0..<width {
                blend(x: x, y: y, tone: shadow, alpha: coverage(x - 1, y - 1))
                blend(x: x, y: y, tone: text, alpha: coverage(x, y))
            }
        }
        return output
    }
}
