import Foundation

/// An Analyze 7.5 or two-file NIfTI-1 volume: a header, `name.hdr`, and its voxels in `name.img`
/// beside it. `-[DicomFile getAnalyze]` and `-getNIfTI` find the image from the header's path, so
/// wherever the database moves or copies a header under a new name, the image has to go with it,
/// under the same name (#642). Taken on its own, an `.img` is not a file the database can index.
@objc(HorosHeaderImagePair)
public final class HeaderImagePair: NSObject {
    /// The image beside a header: the existing `.img` (or `.IMG`) with the header's name, or nil
    /// when `path` is not a `.hdr` or has no image beside it.
    @objc(imagePathForHeader:)
    public static func imagePath(forHeader path: String?) -> String? {
        sibling(of: path, extension: "hdr", wanted: "img")
    }

    /// The header beside an image: the existing `.hdr` (or `.HDR`) with the image's name, or nil when
    /// `path` is not an `.img` or has no header beside it. Such an image is carried by its header.
    @objc(headerPathForImage:)
    public static func headerPath(forImage path: String?) -> String? {
        sibling(of: path, extension: "img", wanted: "hdr")
    }

    /// Where the image of a header stored at `header` belongs: its name with `.img`, which is the
    /// path the readers open.
    @objc(imagePathBesideStoredHeader:)
    public static func imagePath(besideStoredHeader header: String) -> String {
        ((header as NSString).deletingPathExtension as NSString).appendingPathExtension("img") ?? header
    }

    private static func sibling(of path: String?, extension own: String, wanted: String) -> String? {
        guard let path, !path.isEmpty else { return nil }
        let nsPath = path as NSString
        guard nsPath.pathExtension.lowercased() == own else { return nil }
        let base = nsPath.deletingPathExtension as NSString
        let manager = FileManager.default
        for candidate in [wanted, wanted.uppercased()] {
            guard let sibling = base.appendingPathExtension(candidate) else { continue }
            var directory: ObjCBool = false
            if manager.fileExists(atPath: sibling, isDirectory: &directory), !directory.boolValue {
                return sibling
            }
        }
        return nil
    }
}
