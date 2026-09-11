import Foundation

/// Policy and durable admission history for automatic inclusion of prior studies.
/// This records queue admission, not successful delivery: the routing queue owns retries.
@objc(HorosPreviousRoutingStudies)
public final class PreviousRoutingStudies: NSObject {
    private static let lock = NSLock()
    static let interval: TimeInterval = 3 * 60 * 60

    @objc(matchesStudy:currentStudy:modality:description:)
    public static func matches(_ candidate: [String: Any], currentStudy current: [String: Any],
                               modality: Bool, description: Bool) -> Bool {
        guard let date = candidate["date"] as? Date, let currentDate = current["date"] as? Date,
              date < currentDate else { return false }
        func value(_ study: [String: Any], _ key: String) -> String {
            (study[key] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if modality {
            let old = Set(value(candidate, "modality").uppercased().split(separator: "\\").map(String.init))
            let new = Set(value(current, "modality").uppercased().split(separator: "\\").map(String.init))
            guard !old.isEmpty, !old.isDisjoint(with: new) else { return false }
        }
        if description {
            let old = value(candidate, "studyName"), new = value(current, "studyName")
            guard !old.isEmpty, !new.isEmpty,
                  new.range(of: old, options: [.caseInsensitive, .diacriticInsensitive]) != nil else { return false }
        }
        return true
    }

    @objc(reserveStudy:server:databasePath:)
    public static func reserve(study: String, server: [String: Any], databasePath: String) -> Bool {
        reserve(study: study, server: server, databasePath: databasePath, now: Date())
    }

    static func reserve(study: String, server: [String: Any], databasePath: String, now: Date) -> Bool {
        guard !study.isEmpty, !databasePath.isEmpty,
              let address = server["Address"] as? String, !address.isEmpty,
              let ae = server["AETitle"] as? String, !ae.isEmpty else { return false }
        let port = (server["Port"] as? NSNumber)?.stringValue ?? server["Port"] as? String ?? ""
        guard let number = Int(port), (1...65535).contains(number) else { return false }
        // Encode components separately, so punctuation in an AE or UID cannot alias another key.
        let components = [study, address.lowercased(), String(number), ae]
        guard let keyData = try? JSONEncoder().encode(components) else { return false }
        let key = keyData.base64EncodedString()
        let file = URL(fileURLWithPath: databasePath, isDirectory: true)
            .appendingPathComponent("PreviousRoutingStudies.json")
        lock.lock()
        defer { lock.unlock() }
        do {
            var history: [String: Date] = [:]
            if FileManager.default.fileExists(atPath: file.path) {
                history = try JSONDecoder().decode([String: Date].self, from: Data(contentsOf: file))
            }
            history = history.filter { now.timeIntervalSince($0.value) < interval }
            guard history[key] == nil else { return false }
            history[key] = now
            try JSONEncoder().encode(history).write(to: file, options: .atomic)
            return true
        } catch {
            // Do not include patient identifiers, paths or underlying error descriptions in logs.
            NSLog("Autorouting: unable to persist previous-study admission; prior study not queued")
            return false
        }
    }
}
