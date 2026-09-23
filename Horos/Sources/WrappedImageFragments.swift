import AppKit
import ImageIO

/// An image file carried whole in encapsulated Pixel Data, under a private transfer syntax
/// that names no DICOM codec. VTServer 4.32 stores scanned documents this way: a
/// single-page CCITT Group 4 TIFF under 1.2.276.0.19.1.2.55.3. No DICOM decoder reads
/// such an object, so it arrived as not DICOM and an OsiriX server could not send it (#687);
/// ImageIO reads the file inside.
@objc(HorosWrappedImageFragments)
public final class WrappedImageFragments: NSObject {
    /// Whether `syntax` is outside the DICOM root, so no standard codec applies to it.
    @objc(isPrivateTransferSyntax:)
    public static func isPrivateTransferSyntax(_ syntax: String?) -> Bool {
        guard let syntax = syntax?.trimmingCharacters(in: CharacterSet(charactersIn: "\0 ")),
              !syntax.isEmpty else { return false }
        return !syntax.hasPrefix("1.2.840.10008.")
    }

    /// Whether the file at `path` is DICOM that GDCM's scanner refuses only because its
    /// File Meta Information names a private transfer syntax: the dataset reads as
    /// Explicit VR Little Endian and has a Series Instance UID.
    @objc(isDICOMFileWithPrivateTransferSyntaxAtPath:)
    public static func isDICOMFileWithPrivateTransferSyntax(atPath path: String) -> Bool {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe),
              let metadata = DICOMTriageMetadata.parse(data) else { return false }
        return isPrivateTransferSyntax(metadata.string(group: 0x0002, element: 0x0010))
            && metadata.string(group: 0x0020, element: 0x000E) != nil
    }

    /// The image the fragments carry, when the items after the Basic Offset Table form
    /// one image file ImageIO reads and its size is `width` x `height`; nil otherwise.
    @objc(imageFromFragments:width:height:)
    public static func image(fromFragments fragments: [Data], width: Int, height: Int) -> NSImage? {
        guard let image = cgImage(fromFragments: fragments, width: width, height: height) else { return nil }
        return NSImage(cgImage: image, size: NSSize(width: image.width, height: image.height))
    }

    static func cgImage(fromFragments fragments: [Data], width: Int, height: Int) -> CGImage? {
        guard let source = imageSource(fromFragments: fragments, width: width, height: height),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
              image.width == width, image.height == height else { return nil }
        return image
    }

    /// Whether a file's dataset, as the incoming triage parsed it, carries under a private
    /// transfer syntax one image file of `width` x `height` - read from its header, not decoded.
    static func carriesImageFile(_ data: Data, _ metadata: DICOMTriageMetadata, width: Int, height: Int) -> Bool {
        guard isPrivateTransferSyntax(metadata.string(group: 0x0002, element: 0x0010)), metadata.encapsulated,
              var offset = metadata.pixelDataValueOffset, let end = metadata.pixelDataEnd else { return false }
        var fragments: [Data] = []
        while end - offset >= 8 {
            let word = { (at: Int, count: Int) in (0..<count).reduce(0) { $0 | Int(data[at + $1]) << ($1 * 8) } }
            let tag = word(offset, 2) << 16 | word(offset + 2, 2), length = word(offset + 4, 4)
            offset += 8
            if tag == 0xFFFEE0DD { break }
            guard tag == 0xFFFEE000, length <= end - offset else { return false }
            fragments.append(data.subdata(in: offset..<(offset + length)))
            offset += length
        }
        return imageSource(fromFragments: fragments, width: width, height: height) != nil
    }

    /// The items after the Basic Offset Table as one image file ImageIO reads, holding one
    /// image whose header says `width` x `height`.
    private static func imageSource(fromFragments fragments: [Data], width: Int, height: Int) -> CGImageSource? {
        guard fragments.count >= 2, width > 0, height > 0 else { return nil }
        var file = Data()
        for fragment in fragments.dropFirst() { file.append(fragment) }
        guard let source = CGImageSourceCreateWithData(file as CFData, nil),
              CGImageSourceGetType(source) != nil,
              CGImageSourceGetCount(source) == 1,
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              properties[kCGImagePropertyPixelWidth] as? Int == width,
              properties[kCGImagePropertyPixelHeight] as? Int == height else { return nil }
        return source
    }
}
