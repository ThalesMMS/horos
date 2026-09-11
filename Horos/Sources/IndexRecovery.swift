import CoreData
import Foundation

/// What to do when the database index will not open.
///
/// The index is a SQLite file; the images are files beside it. Losing the index
/// loses the studies, the albums, the comments and the ROIs, and it is
/// recoverable from the images only by re-indexing them. So the one thing that
/// must never happen is deleting it — which is what used to happen, on the
/// first failed attempt, whether or not the person at the keyboard agreed, and
/// with no answer to the question that actually matters: *why* it would not
/// open.
///
/// The causes are not interchangeable. A corrupted file has to be replaced. A
/// file the process cannot read, or one whose volume is not there, or a cloud
/// file that has not been downloaded, is intact and will open once the cause is
/// gone: replacing it there would destroy a database that was never damaged.
@objc(HorosIndexRecovery)
public final class IndexRecovery: NSObject {

    /// Where the images live, beside the index.
    private static let dataDirectoryName = "DATABASE.noindex"

    /// A short word for the cause: `corrupt`, `permissions`, `unavailable`,
    /// `migration` or `unknown`.
    @objc(causeForError:)
    public class func cause(forError error: NSError?) -> String {
        guard let error = error else { return "unknown" }
        for candidate in [error] + underlying(of: error) {
            if candidate.domain == NSCocoaErrorDomain {
                switch candidate.code {
                case NSFileReadCorruptFileError, NSPersistentStoreInvalidTypeError,
                     NSPersistentStoreIncompatibleVersionHashError:
                    return "corrupt"
                case NSFileReadNoPermissionError, NSFileWriteNoPermissionError:
                    return "permissions"
                case NSFileReadNoSuchFileError, NSFileNoSuchFileError,
                     NSFileReadInvalidFileNameError:
                    return "unavailable"
                case NSMigrationError, NSMigrationMissingSourceModelError,
                     NSMigrationMissingMappingModelError, NSMigrationManagerSourceStoreError,
                     NSMigrationManagerDestinationStoreError, NSInferredMappingModelError,
                     NSPersistentStoreIncompatibleSchemaError:
                    return "migration"
                default:
                    break
                }
            }
            if candidate.domain == NSPOSIXErrorDomain {
                switch Int32(candidate.code) {
                case EACCES, EPERM: return "permissions"
                case ENOENT, ENODEV, ENXIO, EIO: return "unavailable"
                default: break
                }
            }
        }
        return "unknown"
    }

    /// The line to log, and to show, when the index will not open.
    @objc(diagnosisForError:path:)
    public class func diagnosis(forError error: NSError?, path: String) -> String {
        let name = (path as NSString).lastPathComponent
        let reason = error?.localizedDescription ?? "no reason given"
        switch cause(forError: error) {
        case "corrupt":
            return "\(name) is not readable as a database: \(reason)"
        case "permissions":
            return "\(name) cannot be read with the permissions this process has: \(reason)"
        case "unavailable":
            return "\(name) is not there to be read - an unmounted volume, or a cloud file that "
                + "has not been downloaded: \(reason)"
        case "migration":
            return "\(name) is a database of an older layout that could not be migrated: \(reason)"
        default:
            return "\(name) would not open: \(reason)"
        }
    }

    /// Whether the index may be set aside and rebuilt.
    ///
    /// Only when the file itself is the problem. A file that is intact but
    /// unreachable comes back on its own, and moving it is how a database that
    /// was never damaged gets lost.
    @objc(indexCanBeSetAsideForError:)
    public class func indexCanBeSetAside(forError error: NSError?) -> Bool {
        let cause = self.cause(forError: error)
        return cause == "corrupt" || cause == "migration"
    }

    /// Where to keep the index that would not open. Beside itself, named for
    /// what it is and when, so that more than one attempt does not overwrite
    /// the first - which would be the same loss by another route.
    @objc(preservedPathForIndexAtPath:)
    public class func preservedPath(forIndexAtPath path: String) -> String {
        let stamp = DateFormatter()
        stamp.dateFormat = "yyyy-MM-dd-HHmmss"
        stamp.locale = Locale(identifier: "en_US_POSIX")
        stamp.timeZone = TimeZone(secondsFromGMT: 0)
        var candidate = "\(path).unreadable-\(stamp.string(from: Date()))"
        var attempt = 1
        while FileManager.default.fileExists(atPath: candidate) && attempt < 1000 {
            candidate = "\(path).unreadable-\(stamp.string(from: Date()))-\(attempt)"
            attempt += 1
        }
        return candidate
    }

    /// How many files are in the image directory beside the index, which is what
    /// a rebuild would have to work from; `-1` when there is no such directory.
    ///
    /// This is the count that says whether the studies are recoverable at all,
    /// and it can only be taken before the index is replaced.
    @objc(recoverableFileCountBesideIndexAtPath:)
    public class func recoverableFileCount(besideIndexAtPath path: String) -> Int {
        let directory = ((path as NSString).deletingLastPathComponent as NSString)
            .appendingPathComponent(dataDirectoryName)
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: directory, isDirectory: &isDirectory),
              isDirectory.boolValue,
              let enumerator = FileManager.default.enumerator(atPath: directory) else {
            return -1
        }
        var count = 0
        for case let entry as String in enumerator {
            var entryIsDirectory: ObjCBool = false
            let full = (directory as NSString).appendingPathComponent(entry)
            if FileManager.default.fileExists(atPath: full, isDirectory: &entryIsDirectory),
               !entryIsDirectory.boolValue {
                count += 1
            }
        }
        return count
    }

    private class func underlying(of error: NSError) -> [NSError] {
        var found: [NSError] = []
        if let nested = error.userInfo[NSUnderlyingErrorKey] as? NSError {
            found.append(nested)
            found.append(contentsOf: underlying(of: nested))
        }
        if let several = error.userInfo[NSDetailedErrorsKey] as? [NSError] {
            for nested in several {
                found.append(nested)
                found.append(contentsOf: underlying(of: nested))
            }
        }
        return found
    }
}
