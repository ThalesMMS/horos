import Foundation

/// One identity per volume, one owner per session (#373).
///
/// The migration's planar, MPR and volume viewers (#373, #374, #375) each need
/// to open a series, cache what they decoded, cancel that work and know when it
/// went stale. Left to themselves they grow one loader and one notion of "which
/// volume is this" apiece, and then two of them disagree about whether the user
/// is looking at the same data. This type is the single answer, and it is
/// deliberately small: it decides *identity, ownership, lifetime, invalidation
/// and cancellation*, and nothing else.
///
/// What it does **not** own, on purpose:
///
/// - voxel-to-patient geometry, which is `N3Geometry` / `OSIFloatVolumeData`
///   and already has 29 callers. A second transform stack is exactly the
///   duplication #373 forbids;
/// - pixel decoding and metadata, which are #372's;
/// - ROI and SEG persistence, which is #376's;
/// - the database, albums and scouts, which are #380's. Identity here is
///   *derived* from the DICOM identifiers the database already stores, never
///   invented, so there is no parallel database.
@objc(HorosVolumeIdentity)
public final class VolumeIdentity: NSObject {
    @objc public let studyInstanceUID: String
    @objc public let seriesInstanceUID: String
    /// Empty for a series that declares none. Two volumes with different frames
    /// of reference are different volumes even when the rest matches, which is
    /// what keeps a crosshair from pretending they are registered.
    @objc public let frameOfReferenceUID: String
    /// A 4D series is one volume per time point, not one volume that mutates.
    @objc public let timeIndex: Int
    /// Advances when the series content changes underneath an open session.
    /// Anything cached against an older generation is stale by construction.
    @objc public let generation: Int

    @objc public init?(studyInstanceUID: String,
                       seriesInstanceUID: String,
                       frameOfReferenceUID: String,
                       timeIndex: Int,
                       generation: Int) {
        // The identifiers come from the stored objects. A blank one means the
        // caller is inventing an identity, and two inventions collide.
        let study = studyInstanceUID.trimmingCharacters(in: .whitespacesAndNewlines)
        let series = seriesInstanceUID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !study.isEmpty, !series.isEmpty, timeIndex >= 0, generation >= 0 else { return nil }
        self.studyInstanceUID = study
        self.seriesInstanceUID = series
        self.frameOfReferenceUID = frameOfReferenceUID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.timeIndex = timeIndex
        self.generation = generation
        super.init()
    }

    @objc public convenience init?(studyInstanceUID: String, seriesInstanceUID: String) {
        self.init(studyInstanceUID: studyInstanceUID, seriesInstanceUID: seriesInstanceUID,
                  frameOfReferenceUID: "", timeIndex: 0, generation: 0)
    }

    /// The same volume, one generation on. Used when the series gains or loses
    /// images while somebody is looking at it.
    @objc public func nextGeneration() -> VolumeIdentity {
        VolumeIdentity(studyInstanceUID: studyInstanceUID, seriesInstanceUID: seriesInstanceUID,
                       frameOfReferenceUID: frameOfReferenceUID, timeIndex: timeIndex,
                       generation: generation + 1)!
    }

    /// Same volume, any generation. `isEqual:` is stricter on purpose: a cache
    /// entry must not survive a generation change, while "is the user still on
    /// this series" must not care.
    @objc public func refersToSameVolume(as other: VolumeIdentity) -> Bool {
        studyInstanceUID == other.studyInstanceUID
            && seriesInstanceUID == other.seriesInstanceUID
            && frameOfReferenceUID == other.frameOfReferenceUID
            && timeIndex == other.timeIndex
    }

    public override func isEqual(_ object: Any?) -> Bool {
        guard let other = object as? VolumeIdentity else { return false }
        return refersToSameVolume(as: other) && generation == other.generation
    }

    public override var hash: Int {
        var hasher = Hasher()
        hasher.combine(studyInstanceUID)
        hasher.combine(seriesInstanceUID)
        hasher.combine(frameOfReferenceUID)
        hasher.combine(timeIndex)
        hasher.combine(generation)
        return hasher.finalize()
    }

    public override var description: String {
        "\(studyInstanceUID)/\(seriesInstanceUID)"
            + (frameOfReferenceUID.isEmpty ? "" : "@\(frameOfReferenceUID)")
            + "[t\(timeIndex) g\(generation)]"
    }
}

/// Work a session asked for that may still be in flight.
///
/// Cancellation has to be answerable without reaching the thread doing the
/// work: a cancelled token simply refuses to deliver. That is what makes
/// closing a viewer safe while a decode is running.
@objc(HorosVolumeLoadToken)
public final class VolumeLoadToken: NSObject {
    @objc public let sessionID: Int
    @objc public let identity: VolumeIdentity
    private let lock = NSLock()
    private var cancelled = false
    private var delivered = false

    init(sessionID: Int, identity: VolumeIdentity) {
        self.sessionID = sessionID
        self.identity = identity
        super.init()
    }

    @objc public var isCancelled: Bool {
        lock.lock(); defer { lock.unlock() }
        return cancelled
    }

    @objc public var hasDelivered: Bool {
        lock.lock(); defer { lock.unlock() }
        return delivered
    }

    /// Cancelling after delivery is a no-op, not a rewrite of history: the
    /// caller already has the data and a later `false` would be a lie.
    @objc @discardableResult public func cancel() -> Bool {
        lock.lock(); defer { lock.unlock() }
        if delivered { return false }
        cancelled = true
        return true
    }

    /// `true` only once, and never after cancellation.
    @objc public func deliver() -> Bool {
        lock.lock(); defer { lock.unlock() }
        if cancelled || delivered { return false }
        delivered = true
        return true
    }
}

/// One viewer's hold on one volume.
@objc(HorosVolumeSession)
public final class VolumeSession: NSObject {
    @objc public let sessionID: Int
    @objc public let owner: String
    @objc public private(set) var identity: VolumeIdentity
    @objc public private(set) var isOpen: Bool = true
    private var tokens: [VolumeLoadToken] = []

    init(sessionID: Int, owner: String, identity: VolumeIdentity) {
        self.sessionID = sessionID
        self.owner = owner
        self.identity = identity
        super.init()
    }

    /// True once the series moved on underneath this session. The session stays
    /// open — the viewer is still on screen — but what it cached is not the
    /// current volume any more.
    @objc public private(set) var isStale: Bool = false

    func markStale(currentIdentity: VolumeIdentity) {
        isStale = true
        cancelOutstanding()
        identity = currentIdentity
    }

    func makeToken() -> VolumeLoadToken? {
        guard isOpen else { return nil }
        let token = VolumeLoadToken(sessionID: sessionID, identity: identity)
        tokens.append(token)
        return token
    }

    @discardableResult func cancelOutstanding() -> Int {
        var cancelledCount = 0
        for token in tokens where token.cancel() { cancelledCount += 1 }
        tokens.removeAll { $0.isCancelled || $0.hasDelivered }
        return cancelledCount
    }

    func close() {
        cancelOutstanding()
        isOpen = false
    }
}

/// The single place that hands out sessions.
@objc(HorosVolumeSessionRegistry)
public final class VolumeSessionRegistry: NSObject {
    @objc public static let shared = VolumeSessionRegistry()

    private let lock = NSLock()
    private var sessionsByID: [Int: VolumeSession] = [:]
    private var nextSessionID = 1

    @objc public override init() { super.init() }

    /// Opens, or returns the session this owner already holds for this volume.
    ///
    /// A second owner is refused rather than served: two viewers each believing
    /// they own the volume is how invalidation and cancellation stop meaning
    /// anything. `refusal` says who holds it.
    @objc public func open(identity: VolumeIdentity, owner: String) -> VolumeSession? {
        lock.lock(); defer { lock.unlock() }
        for session in sessionsByID.values
        where session.isOpen && session.identity.refersToSameVolume(as: identity) {
            return session.owner == owner ? session : nil
        }
        let session = VolumeSession(sessionID: nextSessionID, owner: owner, identity: identity)
        nextSessionID += 1
        sessionsByID[session.sessionID] = session
        return session
    }

    @objc public func ownerOfVolume(_ identity: VolumeIdentity) -> String? {
        lock.lock(); defer { lock.unlock() }
        for session in sessionsByID.values
        where session.isOpen && session.identity.refersToSameVolume(as: identity) {
            return session.owner
        }
        return nil
    }

    @objc public func session(withID sessionID: Int) -> VolumeSession? {
        lock.lock(); defer { lock.unlock() }
        return sessionsByID[sessionID]
    }

    @objc public func makeLoadToken(for session: VolumeSession) -> VolumeLoadToken? {
        lock.lock(); defer { lock.unlock() }
        return session.makeToken()
    }

    /// The series changed. Every open session on it is marked stale and its
    /// outstanding work cancelled; the new generation is returned so the caller
    /// can key its cache on it.
    @objc @discardableResult
    public func invalidateVolume(_ identity: VolumeIdentity) -> VolumeIdentity {
        lock.lock(); defer { lock.unlock() }
        let next = identity.nextGeneration()
        for session in sessionsByID.values
        where session.isOpen && session.identity.refersToSameVolume(as: identity) {
            session.markStale(currentIdentity: next)
        }
        return next
    }

    @objc public func close(_ session: VolumeSession) {
        lock.lock(); defer { lock.unlock() }
        session.close()
        sessionsByID.removeValue(forKey: session.sessionID)
    }

    @objc public var openSessionCount: Int {
        lock.lock(); defer { lock.unlock() }
        return sessionsByID.values.filter(\.isOpen).count
    }

    /// Test seam: the shared registry is process-wide, and a suite that leaves
    /// sessions behind makes the next one fail for the wrong reason.
    @objc public func closeAll() {
        lock.lock(); defer { lock.unlock() }
        for session in sessionsByID.values { session.close() }
        sessionsByID.removeAll()
    }
}
