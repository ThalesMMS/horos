import Foundation

/// What became of an archive handed to the importer.
///
/// A `.zip` dropped in the incoming folder is moved aside, expanded into a
/// directory of the same name, and its entries are then imported one by one -
/// possibly spread over several scans, because a scan stops at a file count and
/// at a deadline. Each entry already ends with a line of its own saying whether
/// it was indexed, kept or removed. The archive itself ended with nothing: it
/// left the incoming folder, its expansion emptied out, and the directory was
/// deleted in silence. An archive holding no DICOM at all was therefore
/// indistinguishable, from the outside, from an archive that imported cleanly.
///
/// This keeps the running tally that lets the scan say, once the expansion is
/// exhausted, how many entries the archive held and what happened to them.
/// Tallies are keyed by the absolute path of the expanded directory, so two
/// databases importing archives of the same name do not share a count.
@objc(HorosArchiveImportLedger)
public final class ArchiveImportLedger: NSObject {

    private struct Tally {
        var entries = 0
        var dicom = 0
        var kept = 0
        var deleted = 0
        var nested = 0
    }

    private var tallies: [String: Tally] = [:]
    private let lock = NSLock()

    /// The importer runs on more than one `DicomDatabase` instance - a fresh
    /// independent database is created for each scan - so the tally cannot live
    /// on the instance that happens to be scanning.
    @objc public static let shared = ArchiveImportLedger()

    // MARK: - Recognising archives

    /// Whether `name` names an archive this importer expands.
    @objc public class func isArchiveName(_ name: String) -> Bool {
        let ext = (name as NSString).pathExtension.lowercased()
        return ext == "zip" || ext == "osirixzip"
    }

    /// The expanded archive an entry belongs to, given the entry's path relative
    /// to the incoming folder; `nil` when the entry is not inside one.
    ///
    /// Only the first component counts: an archive is expanded directly into the
    /// incoming folder, and an archive found *within* an archive is moved out and
    /// expanded beside it rather than in place.
    @objc public class func archiveComponent(ofRelativePath path: String) -> String? {
        let components = (path as NSString).pathComponents
        guard components.count > 1, let first = components.first, isArchiveName(first) else {
            return nil
        }
        return first
    }

    // MARK: - Recording

    private func bump(_ archive: String, _ change: (inout Tally) -> Void) {
        lock.lock()
        defer { lock.unlock() }
        var tally = tallies[archive] ?? Tally()
        tally.entries += 1
        change(&tally)
        tallies[archive] = tally
    }

    /// An entry that went into the database.
    @objc(recordIndexedEntryInArchive:)
    public func recordIndexedEntry(inArchive archive: String) {
        bump(archive) { $0.dicom += 1 }
    }

    /// An entry that is DICOM but was handed to the compression queue first. It
    /// comes back to the incoming folder afterwards, no longer inside the
    /// archive's directory, so it is counted here and not again later.
    @objc(recordQueuedEntryInArchive:)
    public func recordQueuedEntry(inArchive archive: String) {
        bump(archive) { $0.dicom += 1 }
    }

    /// An archive inside the archive. It gets a verdict of its own.
    @objc(recordNestedArchiveInArchive:)
    public func recordNestedArchive(inArchive archive: String) {
        bump(archive) { $0.nested += 1 }
    }

    /// An entry this database cannot index, preserved for inspection.
    @objc(recordKeptEntryInArchive:)
    public func recordKeptEntry(inArchive archive: String) {
        bump(archive) { $0.kept += 1 }
    }

    /// An entry this database cannot index, removed.
    @objc(recordDeletedEntryInArchive:)
    public func recordDeletedEntry(inArchive archive: String) {
        bump(archive) { $0.deleted += 1 }
    }

    // MARK: - Reporting

    /// Whether anything has been recorded against this archive.
    @objc(hasArchive:)
    public func hasArchive(_ archive: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return tallies[archive] != nil
    }

    /// The archive's closing line, which also discards the tally: the expansion
    /// is gone by the time this is asked for, and nothing can be added to it.
    ///
    /// `keptDirectoryName` is the folder unreadable files are preserved in, named
    /// so the reader knows where to look rather than being told only that
    /// something was kept.
    @objc(verdictForArchive:keptDirectoryName:)
    public func verdictForArchive(_ archive: String, keptDirectoryName: String) -> String {
        lock.lock()
        let tally = tallies.removeValue(forKey: archive) ?? Tally()
        lock.unlock()

        let name = (archive as NSString).lastPathComponent

        guard tally.entries > 0 else {
            return "\(name): no entries"
        }

        var text = "\(name): \(ArchiveImportLedger.count(tally.entries, "entry", "entries"))"
        text += tally.dicom > 0 ? ", \(tally.dicom) DICOM" : ", no DICOM"

        var dispositions: [String] = []
        if tally.kept > 0 {
            dispositions.append("\(tally.kept) kept in \(keptDirectoryName)")
        }
        if tally.deleted > 0 {
            dispositions.append("\(tally.deleted) deleted")
        }
        if tally.nested > 0 {
            dispositions.append(ArchiveImportLedger.count(tally.nested, "nested archive", "nested archives")
                                + " expanded separately")
        }
        if !dispositions.isEmpty {
            text += "; " + dispositions.joined(separator: ", ")
        }
        return text
    }

    private class func count(_ n: Int, _ singular: String, _ plural: String) -> String {
        return "\(n) \(n == 1 ? singular : plural)"
    }
}
