import Foundation

/// Retrieve-and-view on the host viewer, as one session per requested item (#604).
///
/// Double-clicking a query result starts the configured transport and opens the
/// existing 2D viewer as soon as anything viewable has landed. This type keeps
/// the bookkeeping that the query window, the database importer and the viewer
/// need to agree on, and nothing else: which items are pending, what state each
/// transfer is in, how often the open viewer may reload, and which image the
/// operator was looking at. It opens no window, imports no file and holds no
/// pixels; the query controller, the importer and the viewer keep doing those.
///
/// The state is what the overlay says, so an open viewer never passes for a
/// finished retrieve: *receiving* (instances still expected), *interrupted*
/// (cancelled or ended with losses), *complete* (every expected instance
/// imported and the inventory confirmed) or *unverified* (the peer's counters
/// agree but no confirmed inventory exists).

@objc public enum RetrieveViewingPhase: Int {
    case waiting = 0      // transfer started, nothing local yet
    case receiving        // viewer open, more instances expected
    case interrupted      // cancelled or ended with losses
    case complete         // every expected instance imported, inventory confirmed
    case unverified       // ended without losses reported, inventory unconfirmed
}

@objc(HorosRetrieveViewingState)
public final class RetrieveViewingState: NSObject {
    @objc public let studyInstanceUID: String
    @objc public let seriesInstanceUID: String
    @objc public let phase: RetrieveViewingPhase
    @objc public let localCount: Int
    @objc public let expectedCount: Int
    @objc public let failedCount: Int
    @objc public let inventoryConfirmed: Bool
    @objc public let viewerOpened: Bool

    init(studyInstanceUID: String, seriesInstanceUID: String, phase: RetrieveViewingPhase, localCount: Int,
         expectedCount: Int, failedCount: Int, inventoryConfirmed: Bool, viewerOpened: Bool) {
        self.studyInstanceUID = studyInstanceUID; self.seriesInstanceUID = seriesInstanceUID; self.phase = phase
        self.localCount = localCount; self.expectedCount = expectedCount; self.failedCount = failedCount
        self.inventoryConfirmed = inventoryConfirmed; self.viewerOpened = viewerOpened
        super.init()
    }

    /// What the viewer draws over the image. Empty when nothing is in flight
    /// and the retrieve ended complete, so a finished series looks like any other.
    @objc public var overlayText: String {
        let expected = expectedCount > 0 ? " of \(expectedCount)" : ""
        switch phase {
        case .waiting:
            return NSLocalizedString("Retrieving: waiting for the first image", comment: "retrieve and view overlay")
        case .receiving:
            return String(format: NSLocalizedString("Receiving: %ld%@ instances available, transfer in progress", comment: "retrieve and view overlay"),
                          localCount, expected)
        case .interrupted:
            let losses = failedCount > 0
                ? String(format: NSLocalizedString(", %ld failed", comment: "retrieve and view overlay"), failedCount) : ""
            return String(format: NSLocalizedString("Transfer interrupted: %ld%@ instances available%@", comment: "retrieve and view overlay"),
                          localCount, expected, losses)
        case .complete:
            return ""
        case .unverified:
            return String(format: NSLocalizedString("Transfer ended: %ld instances available, completeness not verified", comment: "retrieve and view overlay"),
                          localCount)
        }
    }

    /// True while MPR/3D must not assume a complete volume.
    @objc public var isPartial: Bool { phase == .waiting || phase == .receiving || phase == .interrupted }
}

/// Reloads of an open viewer are coalesced: at most one per `delay`, and never
/// deferred past `maxDeferral` after the first request, so a steady stream of
/// arrivals still reaches the screen. Pure logic with an injectable clock.
@objc(HorosRefreshCoalescer)
public final class RefreshCoalescer: NSObject {
    @objc public let delay: TimeInterval
    @objc public let maxDeferral: TimeInterval
    private var firstPending: TimeInterval?
    private var lastRequest: TimeInterval?
    private var lastApplied: TimeInterval?
    private(set) var appliedCount = 0

    @objc public init(delay: TimeInterval, maxDeferral: TimeInterval) {
        self.delay = max(0.05, delay)
        self.maxDeferral = max(self.delay, maxDeferral)
        super.init()
    }

    /// The source's defaults: half a second between reloads, two seconds at most.
    @objc public static func standard() -> RefreshCoalescer { RefreshCoalescer(delay: 0.5, maxDeferral: 2) }

    /// Records a request at `now` and returns how long to wait before applying:
    /// 0 when it may run now, otherwise the remaining delay.
    @objc public func request(at now: TimeInterval) -> TimeInterval {
        if firstPending == nil { firstPending = now }
        lastRequest = now
        return waitBeforeApplying(at: now)
    }

    @objc public func waitBeforeApplying(at now: TimeInterval) -> TimeInterval {
        guard let first = firstPending else { return 0 }
        if now - first >= maxDeferral { return 0 }
        guard let applied = lastApplied else { return 0 }   // the first reload runs at once
        let remaining = delay - (now - applied)
        return remaining > 0 ? min(remaining, maxDeferral - (now - first)) : 0
    }

    @objc public var hasPendingRequest: Bool { firstPending != nil }

    /// Called when the reload actually ran.
    @objc public func applied(at now: TimeInterval) {
        lastApplied = now; firstPending = nil; lastRequest = nil; appliedCount += 1
    }

    @objc public var appliedReloads: Int { appliedCount }
}

@objc(HorosRetrieveViewing)
public final class RetrieveViewing: NSObject {
    @objc public static let shared = RetrieveViewing()
    @objc public static let stateDidChangeNotification = Notification.Name("HorosRetrieveViewingStateDidChange")

    private struct Entry {
        var seriesInstanceUID: String
        var phase: RetrieveViewingPhase
        var localCount = 0
        var expectedCount = 0
        var failedCount = 0
        var inventoryConfirmed = false
        var viewerOpened = false
        var cancelled = false
        var startedAt: TimeInterval
        var firstImageAt: TimeInterval?
        var finishedAt: TimeInterval?
        var reloads = 0
    }

    private let lock = NSLock()
    private var entries: [String: Entry] = [:]
    private var lastImportNudge: TimeInterval = 0

    private static func key(_ study: String, _ series: String) -> String { study + "|" + series }

    // MARK: pending items

    /// The item was double-clicked. Idempotent for the same study/series.
    @objc(beginStudyUID:seriesUID:at:)
    @discardableResult
    public func begin(studyUID: String, seriesUID: String, at now: TimeInterval) -> Bool {
        guard !studyUID.isEmpty else { return false }
        lock.lock(); defer { lock.unlock() }
        let key = Self.key(studyUID, seriesUID)
        if let existing = entries[key], existing.finishedAt == nil { return false }
        entries[key] = Entry(seriesInstanceUID: seriesUID, phase: .waiting, startedAt: now)
        return true
    }

    /// Pending: transfer running (or just ended) and the viewer is not yet open.
    @objc public var pendingStudyUIDs: [String] {
        lock.lock(); defer { lock.unlock() }
        return entries.filter { !$0.value.viewerOpened && $0.value.finishedAt == nil }.map { $0.key.components(separatedBy: "|")[0] }
    }

    @objc(isPendingStudyUID:seriesUID:)
    public func isPending(studyUID: String, seriesUID: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard let entry = entries[Self.key(studyUID, seriesUID)] else { return false }
        return !entry.viewerOpened && entry.finishedAt == nil
    }

    /// Whether a database batch carrying these studies concerns a pending item.
    @objc(concernsPendingStudyUIDs:)
    public func concernsPending(studyUIDs: [String]) -> Bool {
        lock.lock(); defer { lock.unlock() }
        let wanted = Set(studyUIDs)
        return entries.contains { entry in
            !entry.value.viewerOpened && entry.value.finishedAt == nil
                && wanted.contains(entry.key.components(separatedBy: "|")[0])
        }
    }

    // MARK: transitions

    @objc(viewerOpenedForStudyUID:seriesUID:localCount:at:)
    public func viewerOpened(studyUID: String, seriesUID: String, localCount: Int, at now: TimeInterval) {
        update(studyUID, seriesUID) { entry in
            entry.viewerOpened = true
            entry.localCount = max(entry.localCount, localCount)
            if entry.firstImageAt == nil { entry.firstImageAt = now }
            if entry.finishedAt == nil { entry.phase = .receiving }
        }
    }

    @objc(localCountChangedForStudyUID:seriesUID:localCount:)
    public func localCountChanged(studyUID: String, seriesUID: String, localCount: Int) {
        update(studyUID, seriesUID) { entry in
            entry.localCount = localCount
            entry.reloads += 1
            if entry.finishedAt != nil { entry.phase = Self.finalPhase(entry) }
        }
    }

    /// The transfer thread ended. `failed` counts sub-operations the peer or the
    /// receiver reported as failed; `expected` the peer's announced total.
    @objc(transferEndedForStudyUID:seriesUID:cancelled:received:expected:failed:inventoryConfirmed:localCount:at:)
    public func transferEnded(studyUID: String, seriesUID: String, cancelled: Bool, received: Int, expected: Int,
                              failed: Int, inventoryConfirmed: Bool, localCount: Int, at now: TimeInterval) {
        update(studyUID, seriesUID) { entry in
            entry.finishedAt = now
            entry.expectedCount = max(entry.expectedCount, expected)
            entry.failedCount = failed
            entry.inventoryConfirmed = inventoryConfirmed
            entry.localCount = max(entry.localCount, localCount)
            entry.cancelled = cancelled
            entry.phase = Self.finalPhase(entry)
        }
    }

    private static func finalPhase(_ entry: Entry) -> RetrieveViewingPhase {
        if entry.cancelled { return .interrupted }
        if entry.failedCount > 0 { return .interrupted }
        if entry.expectedCount > 0 && entry.localCount < entry.expectedCount { return .interrupted }
        if entry.inventoryConfirmed && entry.expectedCount > 0 && entry.localCount >= entry.expectedCount { return .complete }
        return .unverified
    }

    @objc(expectedCountForStudyUID:seriesUID:expected:)
    public func expectedCount(studyUID: String, seriesUID: String, expected: Int) {
        update(studyUID, seriesUID) { $0.expectedCount = max($0.expectedCount, expected) }
    }

    /// The viewer that showed this item closed, or the item was dropped: the
    /// transfer itself is shared and keeps running; only the viewing stops.
    @objc(forgetStudyUID:seriesUID:)
    public func forget(studyUID: String, seriesUID: String) {
        lock.lock(); entries.removeValue(forKey: Self.key(studyUID, seriesUID)); lock.unlock()
        notify(studyUID)
    }

    @objc public func forgetAll() {
        lock.lock(); entries.removeAll(); lock.unlock()
    }

    private func update(_ study: String, _ series: String, _ change: (inout Entry) -> Void) {
        lock.lock()
        var found = false
        if var entry = entries[Self.key(study, series)] {
            change(&entry); entries[Self.key(study, series)] = entry; found = true
        } else if series.isEmpty == false, var entry = entries[Self.key(study, "")] {
            // A study item covers every series that lands under it.
            change(&entry); entries[Self.key(study, "")] = entry; found = true
        }
        lock.unlock()
        if found { notify(study) }
    }

    private func notify(_ study: String) {
        NotificationCenter.default.post(name: Self.stateDidChangeNotification, object: study)
    }

    // MARK: state

    @objc(stateForStudyUID:seriesUID:)
    public func state(studyUID: String, seriesUID: String) -> RetrieveViewingState? {
        lock.lock(); defer { lock.unlock() }
        let entry = entries[Self.key(studyUID, seriesUID)] ?? entries[Self.key(studyUID, "")]
        guard let entry else { return nil }
        return RetrieveViewingState(studyInstanceUID: studyUID, seriesInstanceUID: entry.seriesInstanceUID, phase: entry.phase,
                                    localCount: entry.localCount, expectedCount: entry.expectedCount, failedCount: entry.failedCount,
                                    inventoryConfirmed: entry.inventoryConfirmed, viewerOpened: entry.viewerOpened)
    }

    /// Seconds from the double-click to the first usable image, or -1.
    @objc(secondsToFirstImageForStudyUID:seriesUID:)
    public func secondsToFirstImage(studyUID: String, seriesUID: String) -> Double {
        lock.lock(); defer { lock.unlock() }
        guard let entry = entries[Self.key(studyUID, seriesUID)], let first = entry.firstImageAt else { return -1 }
        return first - entry.startedAt
    }

    @objc(reloadsForStudyUID:seriesUID:)
    public func reloads(studyUID: String, seriesUID: String) -> Int {
        lock.lock(); defer { lock.unlock() }
        return entries[Self.key(studyUID, seriesUID)]?.reloads ?? 0
    }

    // MARK: import nudging

    /// A C-STORE for a pending study just completed. The importer runs on a
    /// timer; nudging it makes the instance visible sooner. Throttled so a burst
    /// of stores asks once, and only while something is pending or receiving.
    @objc(importNudgeWantedForStudyUID:at:)
    public func importNudgeWanted(studyUID: String, at now: TimeInterval) -> Bool {
        lock.lock(); defer { lock.unlock() }
        let live = entries.contains { $0.key.hasPrefix(studyUID + "|") && $0.value.finishedAt == nil }
        guard live, now - lastImportNudge >= 0.5 else { return false }
        lastImportNudge = now
        return true
    }

    // MARK: selection

    /// Where the operator's image is in the reloaded list, so a reload does not
    /// move the selection. Identity is the SOP instance plus the frame; the index
    /// alone is meaningless when instances arrive out of order.
    @objc(indexOfSOPInstanceUID:frame:inSOPInstanceUIDs:frames:fallback:)
    public static func index(ofSOPInstanceUID sop: String, frame: Int, inSOPInstanceUIDs sops: [String], frames: [NSNumber],
                             fallback: Int) -> Int {
        guard !sop.isEmpty else { return min(max(fallback, 0), max(sops.count - 1, 0)) }
        for (index, candidate) in sops.enumerated() where candidate == sop {
            if frames.count > index, frames[index].intValue == frame { return index }
        }
        if let first = sops.firstIndex(of: sop) { return first }
        return min(max(fallback, 0), max(sops.count - 1, 0))
    }
}
