import Foundation

/// A DICOM file whose bytes after the dataset's Pixel Data do not parse - a block of
/// zeros, or part of another file written past the image - is intact up to the end of
/// Pixel Data. DCMTK refuses the whole file, so the import sent it to NOT READABLE and
/// an OsiriX server holding one cannot send it: its study stays at 99% (#687).
@objc(HorosTrailingDataRepair)
public final class DICOMTrailingDataRepair: NSObject {
    /// The length of the file up to the end of its dataset's Pixel Data, when more bytes
    /// follow; nil when nothing follows, there is no Pixel Data, or Pixel Data is not
    /// complete - a truncated image is not repaired.
    @objc(intactLengthOfFileAtPath:)
    public static func intactLength(ofFileAt path: String) -> NSNumber? {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe),
              let end = intactLength(of: data) else { return nil }
        return NSNumber(value: end)
    }

    static func intactLength(of data: Data) -> Int? {
        guard let metadata = DICOMTriageMetadata.parse(data),
              let end = metadata.pixelDataEnd, end < data.count else { return nil }
        return end
    }

    /// Writes the intact part of `path` to `destination`, which must not exist. Returns
    /// the number of bytes left out, or -1 when the file is not one this repairs or the
    /// copy could not be written. `path` itself is only read.
    @objc(writeIntactCopyOfFileAtPath:toPath:)
    public static func writeIntactCopy(ofFileAt path: String, to destination: String) -> Int64 {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe),
              let end = intactLength(of: data) else { return -1 }
        do {
            try data.prefix(end).write(to: URL(fileURLWithPath: destination), options: .withoutOverwriting)
        } catch {
            return -1
        }
        return Int64(data.count - end)
    }
}
