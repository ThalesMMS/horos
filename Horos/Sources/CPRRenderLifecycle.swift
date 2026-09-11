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
@objc(HorosCPRRenderLifecycle)
public final class CPRRenderLifecycle: NSObject {
    private static let lock = NSLock()
    private static var sessionPhase = "idle"
    private static var drawDepth: [String: Int] = [:]

    @objc public static var phase: String {
        lock.lock()
        defer { lock.unlock() }
        return sessionPhase
    }

    @objc public static func reset() {
        lock.lock()
        sessionPhase = "idle"
        drawDepth = [:]
        lock.unlock()
    }

    @objc(beginOpeningResampled:)
    public static func beginOpening(resampled: Bool) -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = resampled ? "opening-resampled" : "opening-native"
        return CPRRenderDecision(accepted: true, phase: sessionPhase,
                                  diagnosis: resampled ? "resample accepted" : "no resample")
    }

    @objc public static func markOpen() -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = "open"
        return CPRRenderDecision(accepted: true, phase: sessionPhase, diagnosis: "window open")
    }

    @objc public static func markCurveReady() -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = "curve-ready"
        return CPRRenderDecision(accepted: true, phase: sessionPhase, diagnosis: "curve concluded")
    }

    @objc public static func beginClosing() -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = "closing"
        return CPRRenderDecision(accepted: true, phase: sessionPhase, diagnosis: "window closing")
    }

    @objc public static func markClosed() -> CPRRenderDecision {
        lock.lock()
        defer { lock.unlock() }
        sessionPhase = "closed"
        drawDepth = [:]
        return CPRRenderDecision(accepted: true, phase: sessionPhase, diagnosis: "window closed")
    }

    @objc(beginDrawNamed:)
    public static func beginDraw(named name: String) -> CPRRenderDecision {
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
    public static func endDraw(named name: String) {
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
