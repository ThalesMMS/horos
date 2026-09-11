import Foundation

/// Why a file the database points at could not be opened.
///
/// The browser said one thing for every cause: `not readable: <path>`, and the
/// alert behind it said "No files available (readable) in this series." A study
/// imported as links to a CD says exactly that when the CD is out, which reads as
/// a decoding failure — the study looks broken rather than disconnected, and
/// nothing suggests putting the disc back.
///
/// The three causes are told apart by where the file was supposed to be: in the
/// database's own folder, on a volume that is not mounted, or at a path on a
/// volume that is mounted and no longer holds it.
@objc(HorosMissingFileReason)
public final class MissingFileReason: NSObject {

    /// One sentence saying why this file is not there, in a form that names the
    /// path and, when the file is a link, says so.
    ///
    /// - Parameters:
    ///   - path: where the database says the file is.
    ///   - inDatabaseFolder: whether the database copied the file into its own
    ///     folder. A file that was not copied is a link to wherever it came from.
    @objc(reasonForPath:inDatabaseFolder:)
    public class func reason(forPath path: String?, inDatabaseFolder: Bool) -> String {
        guard let path = path, path.isEmpty == false else {
            return "the database holds no path for it"
        }

        let manager = FileManager.default

        if manager.fileExists(atPath: path) {
            return inDatabaseFolder
                ? "\(path) is in the database folder and could not be read"
                : "\(path) is a link and could not be read"
        }

        if inDatabaseFolder {
            return "\(path) is missing from the database folder"
        }

        // A link into a volume that is not mounted is the removable-media case:
        // the study is not damaged, the disc is out.
        if let volume = volumeOf(path: path), manager.fileExists(atPath: volume) == false {
            return "\(path) is a link into \(volume), which is not mounted"
        }

        return "\(path) is a link and the file is no longer there"
    }

    /// The `/Volumes/<name>` a path lives on, or nil when it is not on one.
    @objc(volumeOfPath:)
    public class func volumeOf(path: String) -> String? {
        let parts = (path as NSString).pathComponents
        guard parts.count >= 3, parts[0] == "/", parts[1] == "Volumes" else { return nil }
        return "/Volumes/" + parts[2]
    }
}
