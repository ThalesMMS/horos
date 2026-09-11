import Foundation

/// Why a directory the database needs could not be made.
///
/// The file system's own answer is often the wrong one to repeat. An external
/// disk that has been ejected under a running database produces *"You don't
/// have permission to save the file"*, which sends the reader to the permissions
/// they have not changed instead of to the disk they unplugged. The message did
/// not name the path either, so there was nothing in it to act on at all.
@objc(HorosStorageFailure)
public final class StorageFailure: NSObject {

    /// A sentence naming the path, and the cause in the terms that can be acted
    /// on: a volume that is not mounted, a place that cannot be written, or
    /// whatever the file system said when it is neither.
    @objc(reasonForError:path:)
    public class func reason(forError error: NSError?, path: String) -> String {
        let said = error?.localizedDescription ?? "no reason given"

        if let volume = volume(ofPath: path), !exists(volume) {
            return "cannot create \(path): the volume \(volume) is not mounted"
        }

        let deepest = deepestExistingAncestor(of: path)
        if let deepest = deepest, !FileManager.default.isWritableFile(atPath: deepest) {
            return "cannot create \(path): \(deepest) is not writable by this process (\(said))"
        }
        if deepest == nil {
            return "cannot create \(path): none of the folders above it exist (\(said))"
        }
        return "cannot create \(path): \(said)"
    }

    /// The mount point a path is on, when it is on one that can go away;
    /// `nil` for the boot volume.
    @objc(volumeOfPath:)
    public class func volume(ofPath path: String) -> String? {
        let components = (path as NSString).pathComponents
        guard components.count >= 3, components[0] == "/", components[1] == "Volumes" else {
            return nil
        }
        return NSString.path(withComponents: Array(components[0...2]))
    }

    /// The nearest folder above `path` that is actually there; `nil` when none
    /// is - which is what an ejected disk looks like from below.
    @objc(deepestExistingAncestorOfPath:)
    public class func deepestExistingAncestor(of path: String) -> String? {
        var current = (path as NSString).deletingLastPathComponent
        while !current.isEmpty && current != "/" {
            if exists(current) { return current }
            let parent = (current as NSString).deletingLastPathComponent
            if parent == current { break }
            current = parent
        }
        return exists("/") ? "/" : nil
    }

    private class func exists(_ path: String) -> Bool {
        var directory: ObjCBool = false
        return FileManager.default.fileExists(atPath: path, isDirectory: &directory) && directory.boolValue
    }
}
