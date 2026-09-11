import AppKit

/// A patient-space point, tied to the same volume identity used by the host.
/// No pixel buffer, managed object or viewer is retained here.
@objc(HorosPatientCrosshairPoint)
public final class PatientCrosshairPoint: NSObject {
    // Specific Objective-C selectors avoid MyPoint.x/y (Float) in untyped legacy arrays.
    @objc(patientX) public let x: Double
    @objc(patientY) public let y: Double
    @objc(patientZ) public let z: Double
    @objc public let identity: VolumeIdentity

    init(x: Double, y: Double, z: Double, identity: VolumeIdentity) {
        self.x = x; self.y = y; self.z = z; self.identity = identity
        super.init()
    }

    @objc public var coordinates: [NSNumber] { [NSNumber(value: x), NSNumber(value: y), NSNumber(value: z)] }
}

/// Shared patient-point state for planar and MPR adapters. The adapters keep
/// the established DCMPix/N3Geometry transforms and their own rendering paths.
@MainActor @objc(HorosPatientCrosshairController)
public final class PatientCrosshairController: NSObject {
    @objc public static let shared = PatientCrosshairController()
    @objc public static let changeNotification = "HorosPatientCrosshairDidChange"
    @objc public private(set) var isVisible = true
    private var point: PatientCrosshairPoint?
    private weak var sourceSession: VolumeSession?
    @objc public private(set) weak var sourceOwner: AnyObject?
    private let defaults: UserDefaults
    private var checksFrameOfReference: Bool
    private var defaultsObserver: NSObjectProtocol?

    @objc public override convenience init() { self.init(defaults: .standard) }

    init(defaults: UserDefaults) {
        self.defaults = defaults
        checksFrameOfReference = defaults.bool(forKey: ViewerReferenceLines.frameOfReferencePreferenceKey)
        super.init()
        defaultsObserver = NotificationCenter.default.addObserver(
            forName: UserDefaults.didChangeNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.refreshFramePolicy() }
        }
    }

    deinit {
        if let defaultsObserver { NotificationCenter.default.removeObserver(defaultsObserver) }
    }

    private func refreshFramePolicy() {
        let checked = defaults.bool(forKey: ViewerReferenceLines.frameOfReferencePreferenceKey)
        guard checked != checksFrameOfReference else { return }
        checksFrameOfReference = checked
        // Redraw even inactive destinations when a previously admitted frame
        // becomes incompatible. Changing the preference does not move slices.
        notify(move: false)
    }

    /// A point becomes unusable as soon as its source closes or changes volume.
    @objc public var currentPoint: PatientCrosshairPoint? {
        guard let point, sourceOwner != nil, let sourceSession,
              sourceSession.isOpen, !sourceSession.isStale,
              sourceSession.identity.isEqual(point.identity) else { return nil }
        return point
    }

    @objc(publishX:y:z:session:owner:)
    @discardableResult public func publish(x: Double, y: Double, z: Double,
                                          session: VolumeSession, owner: AnyObject) -> Bool {
        guard x.isFinite, y.isFinite, z.isFinite, session.isOpen, !session.isStale else { return false }
        point = PatientCrosshairPoint(x: x, y: y, z: z, identity: session.identity)
        sourceSession = session; sourceOwner = owner
        notify(move: true)
        return true
    }

    @objc(setCrosshairVisible:)
    public func setVisible(_ visible: Bool) {
        guard visible != isVisible else { return }
        isVisible = visible
        notify(move: false)
    }

    @objc(clearForOwner:)
    public func clear(owner: AnyObject) {
        guard sourceOwner === owner else { return }
        point = nil; sourceSession = nil; sourceOwner = nil
        notify(move: false)
    }

    @objc(invalidateSession:)
    public func invalidate(session: VolumeSession) {
        guard sourceSession === session else { return }
        point = nil; sourceSession = nil; sourceOwner = nil
        notify(move: false)
    }

    /// Location/crosshair admission is the host's existing same-world policy.
    /// Turning off the frame check remains an explicit operator preference.
    @objc(pointForSession:registered:useFrameOfReference:)
    public func point(for session: VolumeSession, registered: Bool,
                      useFrameOfReference: Bool) -> PatientCrosshairPoint? {
        guard session.isOpen, !session.isStale, let point = currentPoint else { return nil }
        let sameWorld = ViewerReferenceLines.sameThreeDWorld(
            destinationFrame: session.identity.frameOfReferenceUID,
            sourceFrame: point.identity.frameOfReferenceUID,
            destinationStudy: session.identity.studyInstanceUID,
            sourceStudy: point.identity.studyInstanceUID,
            useFrameOfReference: useFrameOfReference)
        return sameWorld || registered ? point : nil
    }

    private func notify(move: Bool) {
        NotificationCenter.default.post(name: Notification.Name(Self.changeNotification),
                                        object: self, userInfo: ["move": move])
    }
}
