import Foundation
import CryptoKit
import CoreData

/// Reconciles a remote identity inventory with transport events and local import.
/// The WADO download manifest describes HTTP attempts; this record describes the
/// study/series that the query window can actually prove is present locally.
@objc(HorosRetrieveInventory)
public final class RetrieveInventory: NSObject {
    private static let lock = NSRecursiveLock()
    private static let cache = NSMapTable<NSString, RetrieveInventory>(keyOptions: .strongMemory, valueOptions: .weakMemory)
    private static var active: [String: RetrieveInventory] = [:]
    private static var observer: NSObjectProtocol?
    private static var saveObserver: NSObjectProtocol?
    private static var changeObserver: NSObjectProtocol?
    private static var importRevision: UInt = 0
    private var lastImportRevision: UInt?
    private var receivers = 0
    private var receiving: Bool { receivers > 0 }
    private var attemptReceived: Set<String> = []
    private var baselineImported: Set<String>?
    private var data: Snapshot
    @objc public let path: String

    private struct Snapshot: Codable {
        var version = 1
        var study: String
        var series: String
        var expected: [String: String]
        var inventoryConfirmed: Bool
        var received: [String: Int] = [:]
        var rejected: [String: [Int]] = [:]
        var storageWarnings: [String: [Int]]? = [:]
        var httpRejected: Set<String>? = []
        var peerResponses: [[String: String]]? = []
        var peerFailed: Set<String>? = []
        var imported: Set<String> = []
        var duplicateInventory: Set<String> = []
        var queried: Date? = Date()
        var updated = Date()
    }

    private init(data: Snapshot, path: String) {
        self.data = data
        self.path = path
        super.init()
    }

    private static func watchImports() {
        if saveObserver == nil {
            saveObserver = NotificationCenter.default.addObserver(forName: .NSManagedObjectContextDidSave, object: nil, queue: nil) { _ in
                lock.lock(); importRevision &+= 1; lock.unlock()
            }
            changeObserver = NotificationCenter.default.addObserver(forName: .NSManagedObjectContextObjectsDidChange, object: nil, queue: nil) { _ in
                lock.lock(); importRevision &+= 1; lock.unlock()
            }
        }
    }

    /// A repaint reuses the reconciled UID set until Core Data changes or saves state.
    @objc public func beginImportRefresh() -> Bool {
        Self.lock.lock(); defer { Self.lock.unlock() }
        guard lastImportRevision != Self.importRevision else { return false }
        lastImportRevision = Self.importRevision
        return true
    }

    @objc public func invalidateImportRefresh() {
        Self.lock.lock(); defer { Self.lock.unlock() }; lastImportRevision = nil
    }

    private static func file(study: String, series: String, endpoint: String, database: String) -> String {
        let key = (try? JSONEncoder().encode([endpoint, study, series])) ?? Data()
        let hash = SHA256.hash(data: key).map { String(format: "%02x", $0) }.joined()
        return URL(fileURLWithPath: database, isDirectory: true)
            .appendingPathComponent("RetrieveManifests", isDirectory: true)
            .appendingPathComponent(hash + ".json").path
    }

    @objc(beginStudy:series:endpoint:database:instances:confirmed:)
    public static func begin(study: String, series: String, endpoint: String, database: String,
                             instances: [[String: String]], confirmed: Bool) -> RetrieveInventory {
        lock.lock(); defer { lock.unlock() }
        watchImports()
        let path = file(study: study, series: series, endpoint: endpoint, database: database)
        var snapshot = Snapshot(study: study, series: series, expected: [:], inventoryConfirmed: confirmed)
        for item in instances {
            guard let uid = item["uid"], !uid.isEmpty, let seriesUID = item["series"], !seriesUID.isEmpty else {
                snapshot.inventoryConfirmed = false
                continue
            }
            if snapshot.expected[uid] != nil { snapshot.duplicateInventory.insert(uid) }
            snapshot.expected[uid] = seriesUID
        }
        if snapshot.expected.isEmpty { snapshot.inventoryConfirmed = false }
        let inventory = load(study: study, series: series, endpoint: endpoint, database: database)
            ?? RetrieveInventory(data: snapshot, path: path)
        snapshot.received = inventory.data.received
        snapshot.rejected = inventory.data.rejected
        snapshot.storageWarnings = inventory.data.storageWarnings
        snapshot.httpRejected = inventory.data.httpRejected
        snapshot.peerResponses = inventory.data.peerResponses
        snapshot.peerFailed = inventory.data.peerFailed
        inventory.data = snapshot
        if !inventory.receiving {
            inventory.attemptReceived = []
            inventory.baselineImported = nil
        }
        inventory.lastImportRevision = nil
        inventory.receivers += 1
        cache.setObject(inventory, forKey: path as NSString)
        active[path] = inventory
        if observer == nil {
            observer = NotificationCenter.default.addObserver(forName: Notification.Name("HorosDICOMStoreCompleted"), object: nil, queue: nil) { note in
                guard let info = note.userInfo, let uid = info["uid"] as? String,
                      let status = info["status"] as? NSNumber else { return }
                lock.lock(); defer { lock.unlock() }
                for entry in active.values where entry.receiving {
                    let study = info["study"] as? String ?? ""
                    let series = info["series"] as? String ?? ""
                    if ((study.isEmpty || status.intValue != 0) && entry.data.expected[uid] != nil) || (study == entry.data.study && (entry.data.series.isEmpty || entry.data.series == series)) {
                        entry.record(uid: uid, status: status.intValue)
                    }
                }
            }
        }
        inventory.save()
        return inventory
    }

    @objc(loadStudy:series:endpoint:database:)
    public static func load(study: String, series: String, endpoint: String, database: String) -> RetrieveInventory? {
        lock.lock(); defer { lock.unlock() }
        watchImports()
        let path = file(study: study, series: series, endpoint: endpoint, database: database)
        if let cached = cache.object(forKey: path as NSString) { return cached }
        guard let bytes = try? Data(contentsOf: URL(fileURLWithPath: path)),
              let snapshot = try? JSONDecoder().decode(Snapshot.self, from: bytes), snapshot.version == 1 else { return nil }
        let result = RetrieveInventory(data: snapshot, path: path)
        cache.setObject(result, forKey: path as NSString)
        return result
    }

    @objc(recordUID:status:)
    public func record(uid: String, status: Int) {
        Self.lock.lock(); defer { Self.lock.unlock() }
        if status == 0 || (status & 0xf000) == 0xb000 { data.received[uid, default: 0] += 1; attemptReceived.insert(uid) }
        if (status & 0xf000) == 0xb000 {
            var warnings = data.storageWarnings ?? [:]; warnings[uid, default: []].append(status); data.storageWarnings = warnings
        } else if status != 0 { data.rejected[uid, default: []].append(status) }
    }

    @objc(recordPeerFailedUID:)
    public func recordPeerFailedUID(_ uid: String) {
        Self.lock.lock(); defer { Self.lock.unlock() }
        if data.peerFailed == nil { data.peerFailed = [] }
        data.peerFailed?.insert(uid)
    }

    @objc(recordHTTPRejectedUID:)
    public func recordHTTPRejectedUID(_ uid: String) {
        Self.lock.lock(); defer { Self.lock.unlock() }
        if data.httpRejected == nil { data.httpRejected = [] }
        data.httpRejected?.insert(uid)
    }

    @objc(recordOperation:status:completed:failed:warnings:remaining:)
    public func record(operation: String, status: UInt, completed: UInt, failed: UInt, warnings: UInt, remaining: UInt) {
        Self.lock.lock(); defer { Self.lock.unlock() }
        if data.peerResponses == nil { data.peerResponses = [] }
        data.peerResponses?.append(["operation":operation,"status":String(status),"completed":String(completed),
                                    "failed":String(failed),"warnings":String(warnings),"remaining":String(remaining)])
    }

    @objc(updateImportedUIDs:)
    public func updateImportedUIDs(_ uids: [String]) {
        Self.lock.lock(); defer { Self.lock.unlock() }
        let imported = Set(uids.filter { !$0.isEmpty })
        if receiving && baselineImported == nil { baselineImported = imported }
        if imported != data.imported { data.imported = imported; save() }
    }

    @objc public func finish() {
        Self.lock.lock(); defer { Self.lock.unlock() }
        receivers = max(receivers - 1, 0)
        if !receiving { Self.active[path] = nil }
        save()
    }

    private func save() {
        data.updated = Date()
        do {
            let url = URL(fileURLWithPath: path)
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            // The persistent record includes the exact reconciliation, not only counters.
            let encoded = try JSONEncoder().encode(data)
            var object = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
            object["missingUIDs"] = missingUIDs
            object["duplicateUIDs"] = duplicateUIDs
            object["rejectedUIDs"] = rejectedUIDs
            object["unexpectedUIDs"] = unexpectedUIDs
            try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]).write(to: url, options: .atomic)
        } catch {
            NSLog("Retrieve manifest could not be saved; in-memory reconciliation remains available")
        }
    }

    @objc public var inventoryConfirmed: Bool { Self.lock.lock(); defer { Self.lock.unlock() }; return data.inventoryConfirmed }
    @objc public var expectedCount: Int { Self.lock.lock(); defer { Self.lock.unlock() }; return data.expected.count }
    @objc public var localUniqueCount: Int { Self.lock.lock(); defer { Self.lock.unlock() }; return data.imported.count }
    @objc public var needsAttention: Bool {
        Self.lock.lock(); defer { Self.lock.unlock() }
        return !inventoryConfirmed || !Set(missingUIDs).subtracting(attemptReceived).subtracting(baselineImported ?? []).isEmpty
    }
    @objc public var importedCount: Int { Self.lock.lock(); defer { Self.lock.unlock() }; return Set(data.expected.keys).intersection(data.imported).count }
    @objc public var missingUIDs: [String] { Self.lock.lock(); defer { Self.lock.unlock() }; return Set(data.expected.keys).subtracting(data.imported).sorted() }
    @objc public var duplicateUIDs: [String] { Self.lock.lock(); defer { Self.lock.unlock() }; return Set(data.received.filter { $0.value > 1 }.keys).union(data.duplicateInventory).sorted() }
    @objc public var rejectedUIDs: [String] { Self.lock.lock(); defer { Self.lock.unlock() }; return Set(data.rejected.keys).union(data.httpRejected ?? []).union(data.peerFailed ?? []).sorted() }
    @objc public var unexpectedUIDs: [String] { Self.lock.lock(); defer { Self.lock.unlock() }; return inventoryConfirmed ? data.imported.union(data.received.keys).subtracting(data.expected.keys).sorted() : [] }
    @objc(matchesReportedCount:)
    public func matchesReportedCount(_ count: Int) -> Bool {
        inventoryConfirmed && (count <= 0 || count == expectedCount)
    }
    @objc public var queriedAt: Date { Self.lock.lock(); defer { Self.lock.unlock() }; return data.queried ?? data.updated }
    @objc public var isComplete: Bool { inventoryConfirmed && expectedCount > 0 && missingUIDs.isEmpty }
    @objc public var missingSeries: [String: [String]] {
        Self.lock.lock(); defer { Self.lock.unlock() }
        return Dictionary(grouping: missingUIDs, by: { data.expected[$0] ?? "" })
    }
    @objc public var summary: String {
        Self.lock.lock(); defer { Self.lock.unlock() }
        if !inventoryConfirmed { return "Inventory unconfirmed: \(localUniqueCount) local unique instances; \(expectedCount) UIDs announced. Completeness cannot be established." }
        let total = String(expectedCount)
        return "\(isComplete ? "Complete" : "Incomplete"): \(importedCount) of \(total) unique instances imported; \(missingUIDs.count) missing, \(duplicateUIDs.count) duplicated, \(rejectedUIDs.count) with recorded rejections, \(data.storageWarnings?.count ?? 0) with storage warnings, \(unexpectedUIDs.count) unexpected."
    }
}
