import Foundation

/// Named outcome of one CPR render or lifecycle step.
@objc(HorosCPRRenderDecision)
public final class CPRRenderDecision: NSObject {
    @objc public let accepted: Bool
    @objc public let phase: String
    @objc public let diagnosis: String

    @objc public init(accepted: Bool, phase: String, diagnosis: String) {
        self.accepted = accepted
        self.phase = phase
        self.diagnosis = diagnosis
    }
}

/// CPR window lifecycle and drawRect reentrancy. Nested draw of the same view
/// is the hang on newer AppKit SDKs; invalid spacing is named, not rewritten.
///
/// The phase and the draw depth belong to one CPR window. They were static
/// once: a second Curved MPR window then shared them, and closing either one
/// left `closed` behind, so every view of the window still on screen had its
/// draw refused and its panels went blank. `CPRController` owns one instance
/// and hands it to its views.
@objc(HorosCPRRenderLifecycle)
public final class CPRRenderLifecycle: NSObject {
    private let lock = NSLock()
    private var sessionPhase = "idle"
    private var drawDepth: [String: Int] = [:]

    @objc public var phase: String {
        lock.lock()
        defer { lock.unlock() }
        return sessionPhase
    }

    @objc public func reset() {
        lock.lock()
        sessionPhase = "idle"
        drawDepth = [:]
        lock.unlock()
    }

    @objc(beginOpeningResampled:)
    public func beginOpening(resampled: Bool) -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = resampled ? "opening-resampled" : "opening-native"
        return CPRRenderDecision(accepted: true, phase: sessionPhase,
                                  diagnosis: resampled ? "resample accepted" : "no resample")
    }

    @objc public func markOpen() -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = "open"
        return CPRRenderDecision(accepted: true, phase: sessionPhase, diagnosis: "window open")
    }

    @objc public func markCurveReady() -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = "curve-ready"
        return CPRRenderDecision(accepted: true, phase: sessionPhase, diagnosis: "curve concluded")
    }

    @objc public func beginClosing() -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = "closing"
        return CPRRenderDecision(accepted: true, phase: sessionPhase, diagnosis: "window closing")
    }

    @objc public func markClosed() -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = "closed"
        drawDepth = [:]
        return CPRRenderDecision(accepted: true, phase: sessionPhase, diagnosis: "window closed")
    }

    @objc(beginDrawNamed:)
    public func beginDraw(named name: String) -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        if sessionPhase == "closing" || sessionPhase == "closed" {
            return CPRRenderDecision(accepted: false, phase: sessionPhase,
                                     diagnosis: "window closing")
        }
        let depth = drawDepth[name, default: 0]
        if depth > 0 {
            return CPRRenderDecision(accepted: false, phase: "reentrant",
                                     diagnosis: "drawRect recursion")
        }
        drawDepth[name] = depth + 1
        return CPRRenderDecision(accepted: true, phase: "drawing", diagnosis: "draw")
    }

    @objc(endDrawNamed:)
    public func endDraw(named name: String) {
        lock.lock()
        defer { lock.unlock() }
        let depth = drawDepth[name, default: 0]
        drawDepth[name] = max(0, depth - 1)
    }

    @objc(shouldDisplaySynchronouslyWhileDrawing:)
    public static func shouldDisplaySynchronously(whileDrawing drawing: Bool) -> Bool {
        !drawing
    }

    @objc(diagnoseSpacingX:spacingY:)
    public static func diagnoseSpacingX(_ spacingX: Double, spacingY: Double) -> String {
        if spacingX.isNaN || spacingY.isNaN || spacingX.isInfinite || spacingY.isInfinite {
            return "not a number"
        }
        if spacingX <= 0 || spacingY <= 0 {
            return "invalid spacing"
        }
        if spacingX > 1000 || spacingY > 1000 {
            return "out of range"
        }
        return "ready"
    }

    @objc(classifyHangStack:)
    public static func classifyHangStack(_ stack: String) -> String {
        let lowered = stack.lowercased()
        let drawCount = lowered.components(separatedBy: "drawrect").count - 1
        if drawCount >= 2 {
            return "drawrect-recursion"
        }
        return "unclassified"
    }
}
