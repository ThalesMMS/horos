import Foundation

/// Whether a database location is one worth remembering.
///
/// The list of sources is written to the preferences whenever a database is
/// opened that is not already in it, and it is never cleaned. A CD is copied to
/// a folder under the user's temporary directory and opened from there, so
/// inserting one leaves a permanent entry pointing at a path that stops existing
/// when the media is ejected - or when the system cleans its temporary folders,
/// which it does without asking. Those are the unavailable entries that
/// accumulate and cannot be got rid of by removing the media.
///
/// A database on an external disk is a different thing: it is meant to be
/// remembered, listed while the disk is away, and removed deliberately.
@objc(HorosSourceLocation)
public final class SourceLocation: NSObject {

    /// Whether the path is somewhere the system may empty on its own.
    @objc(isTemporaryLocation:)
    public class func isTemporaryLocation(_ path: String?) -> Bool {
        guard let path = path, !path.isEmpty else { return false }
        let candidate = resolved(path)
        for root in temporaryRoots() where candidate.hasPrefix(root) {
            return true
        }
        return false
    }

    /// The entries of the remembered-sources list that are worth keeping: the
    /// permanent ones, without repetitions.
    @objc(permanentEntriesIn:pathKey:)
    public class func permanentEntries(in entries: [[String: Any]], pathKey: String) -> [[String: Any]] {
        var kept: [[String: Any]] = []
        var seen = Set<String>()
        for entry in entries {
            guard let path = entry[pathKey] as? String else { continue }
            if isTemporaryLocation(path) { continue }
            if seen.contains(path) { continue }
            seen.insert(path)
            kept.append(entry)
        }
        return kept
    }

    /// The ones that were dropped, so that what happened can be said rather than
    /// only done.
    @objc(temporaryEntriesIn:pathKey:)
    public class func temporaryEntries(in entries: [[String: Any]], pathKey: String) -> [String] {
        return entries.compactMap { $0[pathKey] as? String }.filter { isTemporaryLocation($0) }
    }

    private class func temporaryRoots() -> [String] {
        var roots = [resolved(NSTemporaryDirectory()), resolved("/tmp")]
        // The per-user folder the system hands out sits under this, and a path
        // can name it directly rather than through NSTemporaryDirectory().
        roots.append("/private/var/folders/")
        return roots.filter { !$0.isEmpty }
    }

    private class func resolved(_ path: String) -> String {
        var resolved = (path as NSString).resolvingSymlinksInPath
        if !resolved.hasSuffix("/") { resolved += "/" }
        return resolved
    }
}
