import Foundation

/// The files an import looked at and did not index, and why.
///
/// `-[DicomDatabase addFilesAtPaths:…]` builds a dictionary for every path it is
/// given and drops the ones it cannot. The drop was silent unless the file was
/// already inside the database folder, so a medium carrying damaged files
/// produced a study with fewer images in it and nothing to say which files were
/// left out. Measured on a disc holding six good instances and five broken ones,
/// the import indexed seven and said nothing about the four it refused.
///
/// A file is refused for different reasons and they are not equally alarming: a
/// text file with a `.dcm` name is a labelling mistake, an empty one is a
/// transfer that never happened, and a DICOM the parser gives up on is a damaged
/// disc. So each refusal is looked at and named.
@objc(HorosImportRefusals)
public final class ImportRefusals: NSObject {

    private struct Refusal {
        let path: String
        let reason: String
    }

    /// How many are named before the rest are counted. A folder of a thousand
    /// snapshots should not print a thousand lines.
    private static let namedAtMost = 8

    private var refusals: [Refusal] = []
    private let lock = NSLock()

    /// How many files the import was given. Settable, because a scan only knows
    /// how many it opened once it has finished opening them.
    @objc public var considered: Int = 0

    @objc public init(considered: Int) {
        self.considered = considered
    }

    @objc public var count: Int {
        lock.lock(); defer { lock.unlock() }
        return refusals.count
    }

    /// Record a file that was not indexed, working out why from the file itself.
    @objc public func refuse(_ path: String) {
        refuse(path, reason: ImportRefusals.reason(for: path))
    }

    /// The same, when the caller already knows why and the file cannot say it.
    ///
    /// A readable image refused because the database is set to index only DICOM
    /// is not an unreadable file, and calling it one would send someone looking
    /// for a fault in a file that has nothing wrong with it.
    @objc public func refuse(_ path: String, reason: String) {
        lock.lock(); defer { lock.unlock() }
        refusals.append(Refusal(path: path, reason: reason))
    }

    /// Why a file that exists on a medium could not become an instance.
    ///
    /// The order matters: a link to nothing answers no to every other question,
    /// and an empty file has no magic to look for.
    @objc public static func reason(for path: String) -> String {
        let manager = FileManager.default
        if manager.fileExists(atPath: path) == false {
            // The enumerator listed it, so something is there - a link with
            // nothing behind it is the usual answer.
            if let _ = try? manager.destinationOfSymbolicLink(atPath: path) {
                return "is a link to nothing"
            }
            return "is no longer there"
        }
        let attributes = try? manager.attributesOfItem(atPath: path)
        if let size = attributes?[.size] as? Int, size == 0 {
            return "is empty"
        }
        guard let handle = FileHandle(forReadingAtPath: path) else {
            return "cannot be opened"
        }
        defer { try? handle.close() }
        let head = handle.readData(ofLength: 132)
        if head.count >= 132, head[128..<132].elementsEqual("DICM".utf8) {
            return "is DICOM the parser could not read"
        }
        // A file written without the 128-byte preamble is still DICOM, and the
        // parser is the one that decides. Saying "not DICOM" of a file the parser
        // refused for another reason would be wrong, so this only says what is
        // certain: no magic, and it was not indexed.
        return "was not recognised as DICOM"
    }

    /// One line naming what was left out, or an empty string when nothing was.
    @objc public var summary: String {
        lock.lock(); defer { lock.unlock() }
        guard refusals.isEmpty == false else { return "" }

        let named = refusals.prefix(ImportRefusals.namedAtMost)
            .map { "\(($0.path as NSString).lastPathComponent) \($0.reason)" }
        var sentence = "\(refusals.count) of \(considered) "
                     + "file\(considered == 1 ? "" : "s") "
                     + "could not be indexed: " + named.joined(separator: ", ")
        guard refusals.count > named.count else { return sentence }
        sentence += ", and \(refusals.count - named.count) more"

        // The names stopped before the end, so say what kind of trouble this
        // medium has without listing the rest of it.
        var tally: [String: Int] = [:]
        for refusal in refusals { tally[refusal.reason, default: 0] += 1 }
        let counted = tally.sorted { $0.value == $1.value ? $0.key < $1.key : $0.value > $1.value }
                           .map { "\($0.value) \($0.key)" }
        return sentence + " (" + counted.joined(separator: ", ") + ")"
    }
}
