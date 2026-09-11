import CryptoKit
import Foundation

/// Exporting the studies named by a list of identifiers, and saying what happened.
///
/// The request behind this is five hundred medical record numbers and no wish to
/// find each one by hand. Two things make that safe to run unattended: the list
/// is resolved by identifier and never by name, so two patients who share a name
/// are never merged; and the export leaves a report saying, per identifier, what
/// was found, how many files, how many bytes, and a digest of them, so a run can
/// be checked afterwards instead of trusted.
@objc(HorosBatchExportManifest)
public final class BatchExportManifest: NSObject {
    /// One identifier per line. Blank lines and `#` comments are dropped, and an
    /// identifier written twice is kept once, in the order it was first written -
    /// a list pasted from a spreadsheet usually has both.
    @objc(identifiersFromText:)
    public static func identifiers(fromText text: String) -> [String] {
        var seen = Set<String>()
        var out: [String] = []
        for line in text.components(separatedBy: .newlines) {
            var value = line
            if let hash = value.firstIndex(of: "#") { value = String(value[value.startIndex ..< hash]) }
            // A CSV column, not just a bare list: take the first field.
            if let comma = value.firstIndex(of: ",") { value = String(value[value.startIndex ..< comma]) }
            value = value.trimmingCharacters(in: .whitespaces)
                         .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            guard !value.isEmpty, !seen.contains(value) else { continue }
            seen.insert(value)
            out.append(value)
        }
        return out
    }

    @objc public static let header = ["Identifier", "Status", "PatientNames", "Studies",
                                      "Files", "Bytes", "Digest", "Detail"]

    @objc(rowForIdentifier:status:names:studies:files:bytes:digest:detail:)
    public static func row(identifier: String, status: String, names: [String], studies: Int,
                           files: Int, bytes: Int64, digest: String, detail: String) -> [String] {
        [identifier, status, names.joined(separator: "; "), String(studies),
         String(files), String(bytes), digest, detail]
    }
}

/// A digest of a set of files that does not depend on the order they were read.
///
/// Each file is hashed on its own and the hexadecimal digests are sorted before
/// being hashed together, so two runs that enumerate the same files in different
/// orders produce the same answer - and a file that changed, went missing or
/// arrived produces a different one.
@objc(HorosFileSetDigest)
public final class FileSetDigest: NSObject {
    private var digests: [String] = []
    @objc public private(set) var fileCount: Int = 0
    @objc public private(set) var byteCount: Int64 = 0
    /// Files that could not be read, by path, in the order they failed.
    @objc public private(set) var unreadable: [String] = []

    @objc(addFileAtPath:)
    @discardableResult
    public func add(path: String) -> Bool {
        guard let handle = FileHandle(forReadingAtPath: path) else {
            unreadable.append(path)
            return false
        }
        defer { try? handle.close() }
        var hasher = SHA256()
        var read: Int64 = 0
        while true {
            guard let chunk = try? handle.read(upToCount: 1 << 20), !chunk.isEmpty else { break }
            hasher.update(data: chunk)
            read += Int64(chunk.count)
        }
        digests.append(hasher.finalize().map { String(format: "%02x", $0) }.joined())
        fileCount += 1
        byteCount += read
        return true
    }

    /// The digest of everything added so far, or an empty string when nothing was.
    @objc public var hexDigest: String {
        guard !digests.isEmpty else { return "" }
        var hasher = SHA256()
        for digest in digests.sorted() { hasher.update(data: Data(digest.utf8)) }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}
