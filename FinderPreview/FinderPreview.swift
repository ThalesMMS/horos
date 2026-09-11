import AppKit
import Foundation
import ImageIO

/// Renders a DICOM file for Finder Quick Look and thumbnails.
///
/// The extension process loads this type and never the Horos application. A
/// supported uncompressed or JPEG Baseline object becomes a picture. Any other
/// transfer syntax, or a file that is not a DICOM image, becomes a sentence
/// that names the reason — not a field of leftover bytes.
public enum FinderPreview {
    public struct Reason: Equatable {
        public let sentence: String
        public let transferSyntax: String?

        public init(sentence: String, transferSyntax: String? = nil) {
            self.sentence = sentence
            self.transferSyntax = transferSyntax
        }
    }

    public enum Outcome: Equatable {
        case image(NSImage)
        case failure(Reason)
    }

    public static let implicitLittleEndian = "1.2.840.10008.1.2"
    public static let explicitLittleEndian = "1.2.840.10008.1.2.1"
    public static let explicitBigEndian = "1.2.840.10008.1.2.2"
    public static let jpegBaseline = "1.2.840.10008.1.2.4.50"

    public static func load(_ url: URL) -> Outcome {
        let data: Data
        do {
            data = try Data(contentsOf: url, options: .mappedIfSafe)
        } catch {
            return .failure(Reason(sentence: Self.unreadableFile))
        }
        return load(data: data)
    }

    public static func load(data: Data) -> Outcome {
        guard data.count >= 132, data[128..<132].elementsEqual(Array("DICM".utf8)) else {
            return .failure(Reason(sentence: Self.notDicom))
        }
        var reader = Reader(data: data, offset: 132, littleEndian: true, explicitVR: true)
        let meta = ElementMap()
        guard reader.readDataset(into: meta, stopAfterGroup: 0x0002) else {
            return .failure(Reason(sentence: Self.notDicom))
        }
        let transfer = meta.uid(0x0002, 0x0010) ?? Self.explicitLittleEndian
        guard let syntax = Syntax(uid: transfer) else {
            return .failure(Reason(
                sentence: Self.unsupportedTransferSyntax(transfer),
                transferSyntax: transfer))
        }
        reader.littleEndian = syntax.littleEndian
        reader.explicitVR = syntax.explicitVR
        let dataset = ElementMap()
        guard reader.readDataset(into: dataset, stopAfterGroup: nil) else {
            return .failure(Reason(sentence: Self.notDicom, transferSyntax: transfer))
        }
        if let sop = dataset.uid(0x0008, 0x0016), Self.nonImageStorage.contains(sop) {
            return .failure(Reason(sentence: Self.notAnImage(sop), transferSyntax: transfer))
        }
        guard let pixels = dataset.pixels else {
            return .failure(Reason(sentence: Self.noImageData, transferSyntax: transfer))
        }
        switch syntax.kind {
        case .uncompressed:
            return renderUncompressed(dataset: dataset, pixels: pixels, transfer: transfer)
        case .jpegBaseline:
            return renderJPEG(pixels: pixels, transfer: transfer)
        }
    }

    /// The sentence Finder shows when the encoding is not one this extension
    /// knows how to turn into a picture.
    public static func unsupportedTransferSyntax(_ uid: String) -> String {
        let format = NSLocalizedString(
            "This transfer syntax is not supported for Finder preview (%@)",
            comment: "Quick Look failure; %@ is the DICOM transfer syntax UID")
        return String(format: format, uid)
    }

    public static let notDicom = NSLocalizedString(
        "This file is not a DICOM image",
        comment: "Quick Look failure for a file without a DICOM header")
    public static let noImageData = NSLocalizedString(
        "This object carries no image data",
        comment: "Quick Look failure when Pixel Data is absent")
    public static let unreadableFile = NSLocalizedString(
        "This image could not be read",
        comment: "Quick Look failure when the file cannot be opened")

    public static func notAnImage(_ sopClassUID: String) -> String {
        let format = NSLocalizedString(
            "This object is not an image (%@)",
            comment: "Quick Look failure; %@ is the SOP Class UID")
        return String(format: format, sopClassUID)
    }

    public static func unsupportedPhotometric(_ name: String) -> String {
        let format = NSLocalizedString(
            "This photometric interpretation is not supported for Finder preview (%@)",
            comment: "Quick Look failure; %@ is Photometric Interpretation")
        return String(format: format, name)
    }

    public static func shortFrame(_ carried: Int, of needed: Int) -> String {
        let format = NSLocalizedString(
            "The frame carries %d of %d bytes",
            comment: "Quick Look failure; sizes are in bytes")
        return String(format: format, carried, needed)
    }

    private static let nonImageStorage: Set<String> = [
        "1.2.840.10008.5.1.4.1.1.11.1",
        "1.2.840.10008.5.1.4.1.1.88.22",
        "1.2.840.10008.5.1.4.1.1.88.33",
        "1.2.840.10008.5.1.4.1.1.88.40",
        "1.2.840.10008.5.1.4.1.1.88.50",
        "1.2.840.10008.5.1.4.1.1.88.59",
        "1.2.840.10008.5.1.4.1.1.88.67",
        "1.2.840.10008.5.1.4.1.1.66",
        "1.2.840.10008.5.1.4.1.1.4.2",
        "1.2.840.10008.5.1.4.1.1.9.1.1",
        "1.2.840.10008.5.1.4.1.1.9.1.2",
        "1.2.840.10008.5.1.4.1.1.9.1.3",
        "1.2.840.10008.5.1.4.1.1.104.1",
    ]
}

private struct Syntax {
    enum Kind { case uncompressed, jpegBaseline }
    let littleEndian: Bool
    let explicitVR: Bool
    let kind: Kind

    init?(uid: String) {
        switch uid {
        case FinderPreview.implicitLittleEndian:
            littleEndian = true; explicitVR = false; kind = .uncompressed
        case FinderPreview.explicitLittleEndian:
            littleEndian = true; explicitVR = true; kind = .uncompressed
        case FinderPreview.explicitBigEndian:
            littleEndian = false; explicitVR = true; kind = .uncompressed
        case FinderPreview.jpegBaseline:
            littleEndian = true; explicitVR = true; kind = .jpegBaseline
        default:
            return nil
        }
    }
}

private final class ElementMap {
    var values: [UInt32: Data] = [:]
    var pixels: Data?

    func store(_ group: UInt16, _ element: UInt16, _ data: Data) {
        if group == 0x7FE0 && element == 0x0010 {
            pixels = data
        } else {
            values[(UInt32(group) << 16) | UInt32(element)] = data
        }
    }

    func data(_ group: UInt16, _ element: UInt16) -> Data? {
        values[(UInt32(group) << 16) | UInt32(element)]
    }

    func uid(_ group: UInt16, _ element: UInt16) -> String? {
        guard let data = data(group, element) else { return nil }
        let text = String(decoding: data, as: UTF8.self)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\0 ").union(.whitespacesAndNewlines))
        return text.isEmpty ? nil : text
    }

    func u16(_ group: UInt16, _ element: UInt16, littleEndian: Bool) -> Int? {
        guard let data = data(group, element), data.count >= 2 else { return nil }
        return Int(integer16(data, 0, littleEndian))
    }

    func asciiNumber(_ group: UInt16, _ element: UInt16) -> Double? {
        guard let data = data(group, element) else { return nil }
        let text = String(decoding: data, as: UTF8.self)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\0 ").union(.whitespacesAndNewlines))
        let first = text.split(whereSeparator: { $0 == "\\" }).first.map(String.init) ?? text
        return Double(first)
    }
}

private struct Reader {
    let data: Data
    var offset: Int
    var littleEndian: Bool
    var explicitVR: Bool

    mutating func readDataset(into map: ElementMap, stopAfterGroup: UInt16?) -> Bool {
        while offset + 8 <= data.count {
            let group = peek16(0)
            let element = peek16(2)
            if let limit = stopAfterGroup, group > limit {
                return true
            }
            if group == 0xFFFE && (element == 0xE0DD || element == 0xE00D) {
                offset += 8
                return true
            }
            offset += 4
            guard let header = readValueHeader() else { return false }
            if group == 0xFFFE && element == 0xE000 {
                if header.length == 0xFFFFFFFF {
                    guard readDataset(into: map, stopAfterGroup: nil) else { return false }
                } else {
                    offset += Int(header.length)
                }
                continue
            }
            if group == 0x7FE0 && element == 0x0010 {
                if header.length == 0xFFFFFFFF {
                    let start = offset
                    guard skipSequence() else { return false }
                    map.store(group, element, data.subdata(in: start ..< offset))
                } else {
                    let length = Int(header.length)
                    guard offset + length <= data.count else { return false }
                    map.store(group, element, data.subdata(in: offset ..< offset + length))
                    offset += length
                }
                return true
            }
            if header.length == 0xFFFFFFFF || header.vr == "SQ" {
                if header.length == 0xFFFFFFFF {
                    guard skipSequence() else { return false }
                } else {
                    offset += Int(header.length)
                }
                continue
            }
            let length = Int(header.length)
            guard offset + length <= data.count else { return false }
            if shouldKeep(group, element) {
                map.store(group, element, data.subdata(in: offset ..< offset + length))
            }
            offset += length
        }
        return true
    }

    private func shouldKeep(_ group: UInt16, _ element: UInt16) -> Bool {
        switch (group, element) {
        case (0x0002, 0x0010), (0x0008, 0x0016),
             (0x0028, 0x0002), (0x0028, 0x0004), (0x0028, 0x0006), (0x0028, 0x0008),
             (0x0028, 0x0010), (0x0028, 0x0011),
             (0x0028, 0x0100), (0x0028, 0x0101), (0x0028, 0x0102), (0x0028, 0x0103),
             (0x0028, 0x1050), (0x0028, 0x1051):
            return true
        default:
            return false
        }
    }

    private mutating func readValueHeader() -> (vr: String, length: UInt32)? {
        if explicitVR {
            guard offset + 4 <= data.count else { return nil }
            let vr = String(decoding: data[offset ..< offset + 2], as: UTF8.self)
            offset += 2
            if Self.longVR.contains(vr) {
                guard offset + 6 <= data.count else { return nil }
                offset += 2
                let length = read32()
                return (vr, length)
            }
            guard offset + 2 <= data.count else { return nil }
            let length = UInt32(read16())
            return (vr, length)
        }
        guard offset + 4 <= data.count else { return nil }
        return ("UN", read32())
    }

    private mutating func skipSequence() -> Bool {
        while offset + 8 <= data.count {
            let group = peek16(0)
            let element = peek16(2)
            offset += 4
            let length = read32()
            if group == 0xFFFE && element == 0xE0DD {
                return true
            }
            if group == 0xFFFE && element == 0xE000 {
                if length == 0xFFFFFFFF {
                    var nested = Reader(data: data, offset: offset,
                                        littleEndian: littleEndian, explicitVR: explicitVR)
                    let discarded = ElementMap()
                    guard nested.readDataset(into: discarded, stopAfterGroup: nil) else { return false }
                    offset = nested.offset
                } else {
                    offset += Int(length)
                }
                continue
            }
            if length == 0xFFFFFFFF {
                guard skipSequence() else { return false }
            } else {
                offset += Int(length)
            }
        }
        return false
    }

    private func peek16(_ extra: Int) -> UInt16 {
        integer16(data, offset + extra, littleEndian)
    }

    private mutating func read16() -> UInt16 {
        let value = integer16(data, offset, littleEndian)
        offset += 2
        return value
    }

    private mutating func read32() -> UInt32 {
        let value = integer32(data, offset, littleEndian)
        offset += 4
        return value
    }

    private static let longVR: Set<String> = [
        "OB", "OD", "OF", "OL", "OV", "OW", "SQ", "SV", "UC", "UN", "UR", "UT", "UV",
    ]
}

private func integer16(_ data: Data, _ offset: Int, _ littleEndian: Bool) -> UInt16 {
    let raw = UInt16(data[offset]) | UInt16(data[offset + 1]) << 8
    return littleEndian ? raw : raw.byteSwapped
}

private func integer32(_ data: Data, _ offset: Int, _ littleEndian: Bool) -> UInt32 {
    let raw = UInt32(data[offset])
        | UInt32(data[offset + 1]) << 8
        | UInt32(data[offset + 2]) << 16
        | UInt32(data[offset + 3]) << 24
    return littleEndian ? raw : raw.byteSwapped
}

private func renderUncompressed(dataset: ElementMap, pixels: Data, transfer: String) -> FinderPreview.Outcome {
    let little = transfer != FinderPreview.explicitBigEndian
    let rows = dataset.u16(0x0028, 0x0010, littleEndian: little) ?? 0
    let columns = dataset.u16(0x0028, 0x0011, littleEndian: little) ?? 0
    let samples = dataset.u16(0x0028, 0x0002, littleEndian: little) ?? 1
    let bitsAllocated = dataset.u16(0x0028, 0x0100, littleEndian: little) ?? 8
    let bitsStored = dataset.u16(0x0028, 0x0101, littleEndian: little) ?? bitsAllocated
    let signed = (dataset.u16(0x0028, 0x0103, littleEndian: little) ?? 0) == 1
    let planar = dataset.u16(0x0028, 0x0006, littleEndian: little) ?? 0
    let photometric = dataset.uid(0x0028, 0x0004) ?? "MONOCHROME2"
    let frames = max(1, dataset.u16(0x0028, 0x0008, littleEndian: little) ?? 1)
    guard rows > 0, columns > 0, rows <= 8192, columns <= 8192 else {
        return .failure(FinderPreview.Reason(sentence: FinderPreview.noImageData, transferSyntax: transfer))
    }
    let bytesPerSample = max(1, bitsAllocated / 8)
    let frameBytes = rows * columns * samples * bytesPerSample
    guard pixels.count >= frameBytes else {
        return .failure(FinderPreview.Reason(
            sentence: FinderPreview.shortFrame(pixels.count, of: frameBytes * frames),
            transferSyntax: transfer))
    }
    let frame = pixels.prefix(frameBytes)
    switch photometric {
    case "MONOCHROME1", "MONOCHROME2":
        guard samples == 1, bitsAllocated == 8 || bitsAllocated == 16 else {
            return .failure(FinderPreview.Reason(
                sentence: FinderPreview.unsupportedPhotometric(photometric),
                transferSyntax: transfer))
        }
        let invert = photometric == "MONOCHROME1"
        let center = dataset.asciiNumber(0x0028, 0x1050)
        let width = dataset.asciiNumber(0x0028, 0x1051)
        return grayscaleImage(frame: Data(frame), rows: rows, columns: columns,
                              bitsAllocated: bitsAllocated, bitsStored: bitsStored,
                              signed: signed, littleEndian: little,
                              invert: invert, center: center, width: width,
                              transfer: transfer)
    case "RGB":
        guard samples == 3, bitsAllocated == 8 else {
            return .failure(FinderPreview.Reason(
                sentence: FinderPreview.unsupportedPhotometric(photometric),
                transferSyntax: transfer))
        }
        return rgbImage(frame: Data(frame), rows: rows, columns: columns,
                        planar: planar == 1, transfer: transfer)
    default:
        return .failure(FinderPreview.Reason(
            sentence: FinderPreview.unsupportedPhotometric(photometric),
            transferSyntax: transfer))
    }
}

private func grayscaleImage(frame: Data, rows: Int, columns: Int,
                            bitsAllocated: Int, bitsStored: Int, signed: Bool,
                            littleEndian: Bool, invert: Bool,
                            center: Double?, width: Double?,
                            transfer: String) -> FinderPreview.Outcome {
    var bytes = [UInt8](repeating: 0, count: rows * columns)
    if bitsAllocated == 8 {
        for i in 0 ..< bytes.count {
            var value = Double(frame[i])
            if let center, let width, width != 0 {
                value = windowLevel(value, center: center, width: width)
            }
            if invert { value = 255 - value }
            bytes[i] = UInt8(clamping: Int(value.rounded()))
        }
    } else {
        let storedMax = Double((1 << min(bitsStored, 16)) - 1)
        for i in 0 ..< bytes.count {
            let raw = integer16(frame, i * 2, littleEndian)
            var value: Double
            if signed {
                value = Double(Int16(bitPattern: raw))
            } else {
                value = Double(raw)
            }
            if let center, let width, width != 0 {
                value = windowLevel(value, center: center, width: width)
            } else if signed {
                let low = -storedMax / 2
                value = (value - low) * 255 / max(storedMax, 1)
            } else {
                value = value * 255 / max(storedMax, 1)
            }
            if invert { value = 255 - value }
            bytes[i] = UInt8(clamping: Int(value.rounded()))
        }
    }
    return image(bytes: bytes, rows: rows, columns: columns, samples: 1, transfer: transfer)
}

private func rgbImage(frame: Data, rows: Int, columns: Int, planar: Bool,
                      transfer: String) -> FinderPreview.Outcome {
    var bytes = [UInt8](repeating: 0, count: rows * columns * 3)
    let plane = rows * columns
    if planar {
        for i in 0 ..< plane {
            bytes[i * 3] = frame[i]
            bytes[i * 3 + 1] = frame[plane + i]
            bytes[i * 3 + 2] = frame[plane * 2 + i]
        }
    } else {
        bytes = Array(frame)
    }
    return image(bytes: bytes, rows: rows, columns: columns, samples: 3, transfer: transfer)
}

private func windowLevel(_ value: Double, center: Double, width: Double) -> Double {
    let low = center - width / 2
    let high = center + width / 2
    if value <= low { return 0 }
    if value >= high { return 255 }
    return (value - low) * 255 / width
}

private func renderJPEG(pixels: Data, transfer: String) -> FinderPreview.Outcome {
    guard let jpeg = firstEncapsulatedItem(pixels) ?? jpegPayload(pixels) else {
        return .failure(FinderPreview.Reason(
            sentence: FinderPreview.unsupportedTransferSyntax(transfer),
            transferSyntax: transfer))
    }
    guard let source = CGImageSourceCreateWithData(jpeg as CFData, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        return .failure(FinderPreview.Reason(
            sentence: FinderPreview.unsupportedTransferSyntax(transfer),
            transferSyntax: transfer))
    }
    let image = NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
    return .image(image)
}

private func firstEncapsulatedItem(_ pixels: Data) -> Data? {
    var offset = 0
    var seenTable = false
    while offset + 8 <= pixels.count {
        let group = integer16(pixels, offset, true)
        let element = integer16(pixels, offset + 2, true)
        let length = Int(integer32(pixels, offset + 4, true))
        offset += 8
        if group == 0xFFFE && element == 0xE0DD { return nil }
        if group == 0xFFFE && element == 0xE000 {
            if length < 0 || offset + length > pixels.count { return nil }
            let item = pixels.subdata(in: offset ..< offset + length)
            offset += length
            if !seenTable {
                seenTable = true
                if item.count >= 2 && item[0] == 0xFF && item[1] == 0xD8 {
                    return item
                }
                continue
            }
            return item
        }
        return nil
    }
    return nil
}

private func jpegPayload(_ pixels: Data) -> Data? {
    if pixels.count >= 2 && pixels[0] == 0xFF && pixels[1] == 0xD8 {
        return pixels
    }
    return nil
}

private func image(bytes: [UInt8], rows: Int, columns: Int, samples: Int,
                   transfer: String) -> FinderPreview.Outcome {
    let info = samples == 3
        ? CGImageAlphaInfo.none.rawValue
        : CGImageAlphaInfo.none.rawValue
    let space = samples == 3 ? CGColorSpaceCreateDeviceRGB() : CGColorSpaceCreateDeviceGray()
    guard let provider = CGDataProvider(data: Data(bytes) as CFData),
          let cgImage = CGImage(width: columns, height: rows,
                                bitsPerComponent: 8, bitsPerPixel: 8 * samples,
                                bytesPerRow: columns * samples, space: space,
                                bitmapInfo: CGBitmapInfo(rawValue: info),
                                provider: provider, decode: nil, shouldInterpolate: false,
                                intent: .defaultIntent) else {
        return .failure(FinderPreview.Reason(sentence: FinderPreview.unreadableFile,
                                             transferSyntax: transfer))
    }
    return .image(NSImage(cgImage: cgImage, size: NSSize(width: columns, height: rows)))
}

extension FinderPreview.Outcome {
    public static func == (lhs: FinderPreview.Outcome, rhs: FinderPreview.Outcome) -> Bool {
        switch (lhs, rhs) {
        case (.failure(let a), .failure(let b)):
            return a == b
        case (.image(let a), .image(let b)):
            return a.tiffRepresentation == b.tiffRepresentation
        default:
            return false
        }
    }
}
