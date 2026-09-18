import Foundation

/// What a shared-database request may reach on the computer that shares (#637).
///
/// `DICOM`, `DCMSE` and `MFILE` name files, and `SETVA` names a key path. The
/// server used both as given: an absolute path, or a relative one climbing out
/// with `..`, read any file the app could read, and `SETVA` wrote any key path -
/// with `reportURL` cleared, it deleted whatever path that attribute held. The
/// rules live here, stated once, and `O2DatabaseConnection` asks them before it
/// reads, sends or writes anything.
///
/// What the client sends (`RemoteDicomDatabase.mm`, and the browser and viewer
/// that call it):
/// - a path per image, `DicomImage.path`: `<number>.dcm` (or another extension)
///   for a file in `DATABASE.noindex`, one component; the absolute path the index
///   holds for an image linked in place; `ROIs/<name>` from older clients;
/// - keys: `comment`...`comment4`, `stateText` and `lockedStudy` from the
///   browser's columns; `reportURL` cleared when a report is deleted;
///   `isKeyImage`, `series.comment`, `series.study.comment` and
///   `series.study.stateText` from the viewer.
@objc(HorosSharedDatabaseRequests)
public final class SharedDatabaseRequests: NSObject {

    /// How `SETVA` writes a key, or `refused`.
    @objc(HorosSharedDatabaseSettableKey)
    public enum SettableKey: Int {
        case refused = 0
        /// A string, or nil.
        case text = 1
        /// An integer, sent as its decimal text.
        case number = 2
        /// `reportURL`: a name inside the reports folder, or nil to delete it.
        case report = 3
    }

    private static let settableKeys: [String: SettableKey] = [
        "comment": .text, "comment2": .text, "comment3": .text, "comment4": .text,
        "series.comment": .text, "series.study.comment": .text,
        "stateText": .number, "series.study.stateText": .number, "lockedStudy": .number, "isKeyImage": .number,
        "reportURL": .report,
    ]

    @objc(settableKindForKey:)
    public class func settableKind(forKey key: String) -> SettableKey {
        settableKeys[key] ?? .refused
    }

    /// Where a report named by a client goes: its last component inside the
    /// reports folder, or nil for a name that would not stay there.
    @objc(reportPathForName:reportsDirectory:)
    public class func reportPath(forName name: String, reportsDirectory: String) -> String? {
        let last = (name as NSString).lastPathComponent
        guard !last.isEmpty, last != ".", last != "..", last != "/" else { return nil }
        return (reportsDirectory as NSString).appendingPathComponent(last)
    }

    /// Whether a stored report path lies inside the reports folder, so clearing
    /// it remotely may delete the file.
    @objc(isPath:insideReportsDirectory:)
    public class func isPath(_ stored: String?, insideReportsDirectory reportsDirectory: String) -> Bool {
        guard let stored, stored.hasPrefix("/"),
              !stored.split(separator: "/").contains(where: { $0 == ".." || $0 == "." }) else { return false }
        let root = (reportsDirectory as NSString).standardizingPath
        return (stored as NSString).standardizingPath.hasPrefix(root.hasSuffix("/") ? root : root + "/")
    }

    /// `DBSIZ` answers in four bytes, which the client reads unsigned. An index of
    /// 4 GiB or more cannot be described in them: the answer is then
    /// `indexTooLargeForReply`, which the client refuses by name, instead of the
    /// size wrapped around.
    @objc public static let indexTooLargeForReply = UInt32.max

    @objc(replyForIndexSize:)
    public class func reply(forIndexSize size: UInt64) -> UInt32 {
        size >= UInt64(UInt32.max) ? indexTooLargeForReply : UInt32(size)
    }
}

/// How a requested path relates to the database.
@objc(HorosSharedDatabasePathKind)
public enum SharedDatabasePathKind: Int {
    /// Not served: empty, a `..` or `.` component, or a relative path of another shape.
    case refused = 0
    /// Inside the database's own folders.
    case database = 1
    /// Absolute and outside them: served only if the index links an image to exactly this path.
    case linked = 2
}

/// The files one request may name, resolved against one database (#637).
///
/// A request can name thousands of paths (`DCMSE` sends one per image), so the
/// folders are resolved once, when the request starts, and each path is looked at
/// once, with the cheapest test that settles it: a relative name is one component
/// or it is refused, and only an absolute path is standardized.
@objc(HorosSharedDatabaseRequestPaths)
public final class SharedDatabaseRequestPaths: NSObject {

    private let dataFolder: NSString
    private let roisFolder: NSString
    private let folderSize: Int
    private let roots: [NSString]

    /// `directory` is the folder of the index (`Database.sql`), whose
    /// `DATABASE.noindex` and `ROIs` the server has always resolved relative paths
    /// into; `dataDirectory` is where the database keeps its files, when elsewhere.
    @objc(initWithDatabaseDirectory:dataDirectory:folderSize:)
    public init(databaseDirectory directory: NSString, dataDirectory: NSString?, folderSize: Int) {
        dataFolder = directory.appendingPathComponent("DATABASE.noindex") as NSString
        roisFolder = directory.appendingPathComponent("ROIs") as NSString
        self.folderSize = folderSize
        var roots = [dataFolder, roisFolder]
        if let dataDirectory, dataDirectory.length > 0 { roots.append(dataDirectory) }
        self.roots = roots.map { root in
            let standardized = root.standardizingPath
            return (standardized.hasSuffix("/") ? standardized : standardized + "/") as NSString
        }
    }

    private static let slash = unichar(UInt8(ascii: "/"))

    /// Whether any component of `path` is `.` or `..`.
    private static func hasDotComponent(_ path: NSString) -> Bool {
        // Most paths hold no "/." at all, and a name cannot start with a dot component otherwise.
        if !path.hasPrefix(".") && path.range(of: "/.").location == NSNotFound { return false }
        for component in path.components(separatedBy: "/") where component == "." || component == ".." {
            return true
        }
        return false
    }

    /// The file a request names, in `path`, and how it relates to the database.
    @objc(kindOfRequestedPath:resolvedPath:)
    public func kind(ofRequestedPath requested: NSString,
                     resolvedPath path: AutoreleasingUnsafeMutablePointer<NSString?>) -> SharedDatabasePathKind {
        path.pointee = nil
        let length = requested.length
        guard length > 0 else { return .refused }

        if requested.character(at: 0) != Self.slash {
            let separator = requested.range(of: "/")
            if separator.location == NSNotFound {
                // An image of DATABASE.noindex, by the name the index gives it.
                guard !requested.isEqual(to: "."), !requested.isEqual(to: "..") else { return .refused }
                let number = Int((requested.deletingPathExtension as NSString).intValue)
                let folder = folderSize > 0 ? (number / folderSize + 1) * folderSize : 0
                path.pointee = "\(dataFolder)/\(folder)/\(requested)" as NSString
                return .database
            }
            // As before, an older client's ROI by its name: "ROIs/<name>".
            guard requested.hasPrefix("ROIs/"), !Self.hasDotComponent(requested) else { return .refused }
            let name = requested.lastPathComponent
            guard !name.isEmpty, name != "ROIs" else { return .refused }
            path.pointee = roisFolder.appendingPathComponent(name) as NSString
            return .database
        }

        guard !Self.hasDotComponent(requested) else { return .refused }
        path.pointee = requested
        // With no dot component left, standardizing only folds repeated slashes and a
        // leading /private: a path without either is already in standard form.
        let standardized = requested.range(of: "//").location == NSNotFound && !requested.hasPrefix("/private/")
            ? requested : requested.standardizingPath as NSString
        for root in roots where standardized.hasPrefix(root as String) {
            return .database
        }
        return .linked
    }
}

/// The absolute paths the index links images to, for the shared-database server
/// (#637): what `DICOM`, `DCMSE` and `MFILE` may read outside the database's
/// folders.
///
/// `pathString` has no index in the store: asking the database whether it links a
/// path scans every image. A request asks that only for the paths not already
/// confirmed, and a confirmed path stays confirmed until the index file changes -
/// the store keeps a rollback journal, so every save rewrites `Database.sql`, and
/// its modification time is read before looking up, never after. A viewer
/// downloading a linked series then pays the lookup once per batch of new paths
/// and not again; nothing is kept for a path the index does not link.
@objc(HorosSharedDatabaseLinkedPaths)
public final class SharedDatabaseLinkedPaths: NSObject {

    @objc(sharedPaths)
    public static let shared = SharedDatabaseLinkedPaths()

    private let lock = NSLock()
    private let confirmed = NSMutableSet()
    private var stamp: (Int, Int, Int)?

    /// Whether the index links an image to every one of `paths`. `indexFile` is
    /// the store (`Database.sql`); `lookup` returns which of the paths it is given
    /// the index links, and is asked only about paths not confirmed since the
    /// store last changed.
    @objc(containsAllPaths:indexFile:lookup:)
    public func containsAll(_ paths: NSSet, indexFile: NSString, lookup: (NSSet) -> [Any]) -> Bool {
        guard paths.count > 0 else { return true }
        var status = stat()
        let current = stat(indexFile.fileSystemRepresentation, &status) == 0
            ? (Int(status.st_mtimespec.tv_sec), Int(status.st_mtimespec.tv_nsec), Int(status.st_size)) : nil
        lock.lock()
        defer { lock.unlock() }
        if current == nil || stamp == nil || current! != stamp! {
            confirmed.removeAllObjects()
            stamp = current
        }
        let unconfirmed = NSMutableSet()
        for path in paths where !confirmed.contains(path) {
            unconfirmed.add(path)
        }
        guard unconfirmed.count > 0 else { return true }
        let linked = NSSet(array: lookup(unconfirmed))
        var missing = false
        for path in unconfirmed {
            if linked.contains(path) { confirmed.add(path) } else { missing = true }
        }
        return !missing
    }
}
