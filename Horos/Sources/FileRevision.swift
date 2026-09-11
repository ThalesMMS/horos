import Foundation

/// The identity of a file's *contents* at the moment they were read (#603).
///
/// A database path can be reused after a deletion, a re-import can replace a
/// file in place, and an external tool can rewrite the bytes under an open
/// viewer. Every cache that was keyed by the pathname alone then answers for
/// the wrong file. This type is the key those caches use instead: the path
/// plus what `stat` says about the inode and its last change. It never reads
/// the file, so it costs one system call, and it is deliberately not a hash of
/// the bytes: hashing every redraw is what #603 forbids when the file system
/// already records the change.
///
/// Both the modification and the change time are kept. A same-size rewrite
/// that preserves `mtime` (a copy tool restoring dates) still moves `ctime`;
/// a rename over the path changes the inode. Sub-second precision comes from
/// the file system, so two rewrites inside the same second are only told
/// apart by their inode or size — that limit is recorded, not hidden.
@objc(HorosFileRevision)
public final class FileRevision: NSObject {
    @objc public let path: String
    @objc public let device: Int
    @objc public let inode: UInt64
    @objc public let size: Int64
    @objc public let modificationSeconds: Int64
    @objc public let modificationNanoseconds: Int64
    @objc public let changeSeconds: Int64
    @objc public let changeNanoseconds: Int64

    /// nil when the file cannot be inspected (missing, unreadable directory).
    @objc public init?(path: String) {
        var status = stat()
        guard !path.isEmpty, path.withCString({ Darwin.fstatat(AT_FDCWD, $0, &status, 0) }) == 0,
              (status.st_mode & S_IFMT) == S_IFREG else { return nil }
        self.path = path
        device = Int(status.st_dev)
        inode = UInt64(status.st_ino)
        size = Int64(status.st_size)
        modificationSeconds = Int64(status.st_mtimespec.tv_sec)
        modificationNanoseconds = Int64(status.st_mtimespec.tv_nsec)
        changeSeconds = Int64(status.st_ctimespec.tv_sec)
        changeNanoseconds = Int64(status.st_ctimespec.tv_nsec)
        super.init()
    }

    /// Path-keyed caches switch to this string: the same path names a
    /// different key as soon as the file underneath it is another file.
    @objc public var cacheKey: String {
        "\(path)|dev=\(device):ino=\(inode):size=\(size)"
            + ":mtime=\(modificationSeconds).\(modificationNanoseconds)"
            + ":ctime=\(changeSeconds).\(changeNanoseconds)"
    }

    /// The key for a path right now, or nil when there is no regular file.
    @objc public static func cacheKey(forPath path: String) -> String? {
        FileRevision(path: path)?.cacheKey
    }

    /// Whether the file on disk is still the one this revision describes.
    @objc public func matchesDisk() -> Bool {
        guard let current = FileRevision(path: path) else { return false }
        return isEqual(current)
    }

    /// Why pixels or geometry loaded from `loaded` must not stand for the file
    /// as it is now, or nil when they may. `current` nil means the file is gone.
    @objc public static func refusalForReusingFile(loaded: FileRevision?, current: FileRevision?) -> String? {
        guard let loaded else { return "Nothing is recorded about the file that was loaded; it cannot be reused." }
        guard let current else { return "The file at \(loaded.path) is no longer there; what was loaded from it cannot stand for it." }
        if loaded.path != current.path {
            return "What was loaded from \(loaded.path) cannot stand for \(current.path)."
        }
        if loaded.device != current.device || loaded.inode != current.inode {
            return "The file at \(loaded.path) was replaced (inode \(loaded.inode) is now \(current.inode)); reload it."
        }
        if loaded.size != current.size {
            return "The file at \(loaded.path) changed size (\(loaded.size) bytes is now \(current.size)); reload it."
        }
        if loaded.modificationSeconds != current.modificationSeconds
            || loaded.modificationNanoseconds != current.modificationNanoseconds
            || loaded.changeSeconds != current.changeSeconds
            || loaded.changeNanoseconds != current.changeNanoseconds {
            return "The file at \(loaded.path) was rewritten since it was loaded; reload it."
        }
        return nil
    }

    public override func isEqual(_ object: Any?) -> Bool {
        guard let other = object as? FileRevision else { return false }
        return path == other.path && device == other.device && inode == other.inode && size == other.size
            && modificationSeconds == other.modificationSeconds
            && modificationNanoseconds == other.modificationNanoseconds
            && changeSeconds == other.changeSeconds && changeNanoseconds == other.changeNanoseconds
    }

    public override var hash: Int { cacheKey.hashValue }

    public override var description: String { cacheKey }
}
