import Foundation

/// Optional search across the local databases the user has chosen.
///
/// Horos keeps one study list per open database. A teaching collection that
/// lives in several folders therefore cannot be queried from the current
/// window or from the web portal unless those folders are asked one by one.
/// This object is the catalogue, the opt-in flags, the identity rule that
/// keeps two patients with the same name apart, and the portal XID that
/// names both a study and the database it came from.
///
/// A query is optional: with no search, the current or portal database is
/// unchanged. Chosen sources are the extra local folders marked
/// `FederatedSearch`. Origin and the caller's permission string travel with
/// every hit so the UI and the portal can show them. Homonyms are never
/// merged by name.
@objc(HorosFederatedSearch)
public final class FederatedSearch: NSObject {
    @objc public static let sourceFlagKey = "FederatedSearch"
    @objc public static let defaultSourceFlagKey = "HorosDefaultDatabaseFederatedSearch"

    /// When the preference has never been written, the default database is
    /// included so a search from a section folder still sees the documents
    /// database that OsiriX used as the waystation.
    @objc public static var isDefaultDatabaseIncluded: Bool {
        get {
            let defaults = UserDefaults.standard
            if defaults.object(forKey: defaultSourceFlagKey) == nil { return true }
            return defaults.bool(forKey: defaultSourceFlagKey)
        }
        set { UserDefaults.standard.set(newValue, forKey: defaultSourceFlagKey) }
    }

    /// One local source the user can opt into a federated query.
    @objc public static func sources(
        fromLocalDatabasePaths paths: [[String: Any]]?,
        defaultPath: String?,
        defaultName: String?,
        defaultIncluded: Bool
    ) -> [[String: Any]] {
        var result: [[String: Any]] = []
        var seen = Set<String>()
        if let defaultPath, let key = canonicalPath(defaultPath), !key.isEmpty {
            seen.insert(key)
            result.append([
                "path": defaultPath,
                "name": displayOrigin(name: defaultName, path: defaultPath),
                "included": defaultIncluded,
                "isDefault": true
            ])
        }
        for entry in paths ?? [] {
            guard let path = string(entry["Path"]), !path.isEmpty else { continue }
            let key = canonicalPath(path) ?? path
            if seen.contains(key) { continue }
            seen.insert(key)
            result.append([
                "path": path,
                "name": displayOrigin(name: string(entry["Description"]), path: path),
                "included": bool(entry[sourceFlagKey]),
                "isDefault": false
            ])
        }
        return result
    }

    @objc public static func includedPaths(
        fromLocalDatabasePaths paths: [[String: Any]]?,
        defaultPath: String?,
        defaultIncluded: Bool
    ) -> [String] {
        sources(
            fromLocalDatabasePaths: paths,
            defaultPath: defaultPath,
            defaultName: nil,
            defaultIncluded: defaultIncluded
        ).compactMap { source in
            guard bool(source["included"]), let path = string(source["path"]) else { return nil }
            return path
        }
    }

    @objc public static func isPath(
        _ path: String?,
        includedIn paths: [[String: Any]]?,
        defaultPath: String?,
        defaultIncluded: Bool
    ) -> Bool {
        guard let path else { return false }
        if pathsEqual(path, defaultPath) { return defaultIncluded }
        for entry in paths ?? [] {
            if pathsEqual(path, string(entry["Path"])) { return bool(entry[sourceFlagKey]) }
        }
        return false
    }

    @objc public static func updatingLocalDatabasePaths(
        _ paths: [[String: Any]]?,
        path: String,
        included: Bool
    ) -> [[String: Any]] {
        var result: [[String: Any]] = []
        var found = false
        for entry in paths ?? [] {
            var next = entry
            if pathsEqual(string(entry["Path"]), path) {
                next[sourceFlagKey] = included
                found = true
            }
            result.append(next)
        }
        if !found {
            result.append(["Path": path, sourceFlagKey: included])
        }
        return result
    }

    @objc(pathsEqual:other:)
    public static func pathsEqual(_ first: String?, _ second: String?) -> Bool {
        guard let left = canonicalPath(first), let right = canonicalPath(second) else {
            return false
        }
        return left == right
    }

    /// Same person in the same study in the same database. Name is not part
    /// of the key: two teaching cases called "Pneumonia" stay two rows when
    /// their patient identifiers differ.
    @objc(identityKeyWithPatientUID:studyUID:originPath:)
    public static func identityKey(patientUID: String?, studyUID: String?, originPath: String?) -> String {
        let origin = canonicalPath(originPath) ?? originPath ?? ""
        return "\(normalized(patientUID))|\(normalized(studyUID))|\(origin)"
    }

    @objc(areHomonymsWithName:patientUID:otherName:otherPatientUID:)
    public static func areHomonyms(
        name: String?,
        patientUID: String?,
        otherName: String?,
        otherPatientUID: String?
    ) -> Bool {
        namesMatch(name, otherName) && !identifiersMatch(patientUID, otherPatientUID)
    }

    /// Keeps every distinct identity. A later hit with the same key is the
    /// same study seen again, not a second patient.
    @objc public static func mergingHits(_ hits: [[String: Any]]) -> [[String: Any]] {
        var seen = Set<String>()
        var result: [[String: Any]] = []
        for hit in hits {
            let key = identityKey(
                patientUID: string(hit["patientUID"]),
                studyUID: string(hit["studyInstanceUID"]),
                originPath: string(hit["originPath"])
            )
            if seen.contains(key) { continue }
            seen.insert(key)
            result.append(hit)
        }
        return result
    }

    @objc public static func hit(
        _ hit: [String: Any],
        matchesQuery query: String?,
        field: String?
    ) -> Bool {
        let term = (query ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !term.isEmpty else { return false }
        switch field ?? "name" {
        case "patientID", "searchID":
            return contains(string(hit["patientID"]), term)
        case "accessionNumber", "searchAccessionNumber":
            return contains(string(hit["accessionNumber"]), term)
        case "studyName":
            return contains(string(hit["studyName"]), term)
        default:
            return contains(string(hit["name"]), term)
        }
    }

    @objc public static func isUnrestrictedPermission(_ predicate: String?) -> Bool {
        let compact = (predicate ?? "")
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "(", with: "")
            .replacingOccurrences(of: ")", with: "")
            .uppercased()
        return compact.isEmpty || compact == "YES==YES"
    }

    @objc public static func permissionLabel(forPredicate predicate: String?) -> String {
        if isUnrestrictedPermission(predicate) { return "unrestricted" }
        let trimmed = (predicate ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "unrestricted" : trimmed
    }

    /// Used by the unit tests for the obvious comment/name filters. The
    /// portal applies the real smart-album NSPredicate against each study.
    @objc public static func studyAllowed(
        byPredicate predicate: String?,
        comment: String?,
        name: String?,
        patientID: String?
    ) -> Bool {
        if isUnrestrictedPermission(predicate) { return true }
        guard let predicate, !predicate.isEmpty else { return true }
        if let value = containsNeedle(in: predicate, key: "comment") {
            return contains(comment, value)
        }
        if let value = containsNeedle(in: predicate, key: "name") {
            return contains(name, value)
        }
        if let value = containsNeedle(in: predicate, key: "patientID") {
            return contains(patientID, value)
        }
        return false
    }

    @objc(federatedXIDWithStudyXID:originPath:)
    public static func federatedXID(studyXID: String, originPath: String) -> String {
        let encoded = Data(originPath.utf8).base64EncodedString()
        return "FED:\(encoded):\(studyXID)"
    }

    @objc public static func isFederatedXID(_ xid: String?) -> Bool {
        (xid ?? "").hasPrefix("FED:")
    }

    @objc public static func originPath(fromFederatedXID xid: String?) -> String? {
        guard let body = federatedBody(xid) else { return nil }
        guard let data = Data(base64Encoded: body.origin) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    @objc public static func studyXID(fromFederatedXID xid: String?) -> String? {
        federatedBody(xid)?.study
    }

    @objc(displayName:origin:currentOrigin:)
    public static func displayName(_ name: String?, origin: String?, currentOrigin: String?) -> String {
        let shown = (name ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let originName = (origin ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !originName.isEmpty else { return shown }
        if let currentOrigin, pathsEqual(origin, currentOrigin) || originName == currentOrigin {
            return shown
        }
        if shown.isEmpty { return originName }
        return "\(shown) — \(originName)"
    }

    @objc public static func displayOrigin(name: String?, path: String?) -> String {
        let trimmed = (name ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { return trimmed }
        let nsPath = (path ?? "") as NSString
        let last = nsPath.lastPathComponent
        if last == DatabaseLocation.dataDirectoryName {
            return (nsPath.deletingLastPathComponent as NSString).lastPathComponent
        }
        return last
    }

    @objc public static func canonicalPath(_ path: String?) -> String? {
        guard var path = path, !path.isEmpty else { return nil }
        path = (path as NSString).standardizingPath
        if let resolved = DatabaseLocation.baseDirectory(forPath: path) {
            path = resolved
        }
        return (path as NSString).standardizingPath.precomposedStringWithCanonicalMapping.lowercased()
    }

    private static func federatedBody(_ xid: String?) -> (origin: String, study: String)? {
        guard let xid, xid.hasPrefix("FED:") else { return nil }
        let rest = xid.dropFirst(4)
        guard let separator = rest.firstIndex(of: ":") else { return nil }
        let origin = String(rest[..<separator])
        let study = String(rest[rest.index(after: separator)...])
        guard !origin.isEmpty, !study.isEmpty else { return nil }
        return (origin, study)
    }

    private static func containsNeedle(in predicate: String, key: String) -> String? {
        let pattern = "\(key) CONTAINS"
        guard let range = predicate.range(of: pattern, options: .caseInsensitive) else { return nil }
        var rest = String(predicate[range.upperBound...])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if rest.hasPrefix("[cd]") || rest.hasPrefix("[c]") {
            rest = String(rest.drop(while: { $0 != " " && $0 != "'" && $0 != "\"" }))
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard let quote = rest.first, quote == "'" || quote == "\"" else { return nil }
        rest.removeFirst()
        guard let end = rest.firstIndex(of: quote) else { return nil }
        return String(rest[..<end])
    }

    private static func namesMatch(_ first: String?, _ second: String?) -> Bool {
        normalized(first).compare(normalized(second), options: [.caseInsensitive, .diacriticInsensitive])
            == .orderedSame && !normalized(first).isEmpty
    }

    private static func identifiersMatch(_ first: String?, _ second: String?) -> Bool {
        normalized(first).compare(normalized(second), options: [.caseInsensitive, .diacriticInsensitive])
            == .orderedSame
    }

    private static func contains(_ value: String?, _ term: String) -> Bool {
        guard let value, !value.isEmpty else { return false }
        return value.range(of: term, options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }

    private static func normalized(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func string(_ value: Any?) -> String? {
        if let value = value as? String { return value }
        return nil
    }

    private static func bool(_ value: Any?) -> Bool {
        if let value = value as? Bool { return value }
        if let value = value as? NSNumber { return value.boolValue }
        if let value = value as? String {
            return (value as NSString).boolValue
        }
        return false
    }
}
