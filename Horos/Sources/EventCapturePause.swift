import AppKit

/// Distinguishes a 1–2 s input hole from a main-thread stall (#286).
///
/// The 2017 report (horosproject/horos#194) saw brush, database scrolling
/// and image scrolling all stop registering events for about a second.
/// That is not the same contract as the database matrix click-hold (1 s)
/// or the thumbnail hold-to-drag (2 s). Those two waits start a drag;
/// they are not a stall during an already-running gesture.
///
/// A gap is only a main-thread stall when the heartbeat stops too. A gap
/// with a live heartbeat is event absence. Neither reading invents a
/// cause — previous use of another application is not treated as proof.
@objc(HorosEventCapturePauseKind)
public enum EventCapturePauseKind: Int {
    case withinCadence = 1
    case eventAbsence = 2
    case mainBlocked = 3
}

@objc(HorosEventCapturePauseSample)
public final class EventCapturePauseSample: NSObject {
    @objc public let drawTicks: Int
    @objc public let heartbeatTicks: Int
    @objc public let maxDrawGap: TimeInterval
    @objc public let maxHeartbeatGap: TimeInterval
    @objc public let duration: TimeInterval
    @objc public let kind: EventCapturePauseKind
    @objc public let backgroundIterations: Int

    @objc public init(
        drawTicks: Int,
        heartbeatTicks: Int,
        maxDrawGap: TimeInterval,
        maxHeartbeatGap: TimeInterval,
        duration: TimeInterval,
        kind: EventCapturePauseKind,
        backgroundIterations: Int
    ) {
        self.drawTicks = drawTicks
        self.heartbeatTicks = heartbeatTicks
        self.maxDrawGap = maxDrawGap
        self.maxHeartbeatGap = maxHeartbeatGap
        self.duration = duration
        self.kind = kind
        self.backgroundIterations = backgroundIterations
        super.init()
    }
}

@objc(HorosEventCapturePause)
public final class EventCapturePause: NSObject {
    @objc public static let historicalPauseMinimum: TimeInterval = 1.0
    @objc public static let historicalPauseMaximum: TimeInterval = 2.0
    @objc public static let databaseClickHoldLimit: TimeInterval = 1.0
    @objc public static let thumbnailHoldToDragLimit: TimeInterval = 2.0
    @objc public static let drawTickInterval: TimeInterval = 0.01

    @objc(classifyEventGap:heartbeatGap:)
    public static func classify(eventGap: TimeInterval, heartbeatGap: TimeInterval) -> EventCapturePauseKind {
        if eventGap < historicalPauseMinimum {
            return .withinCadence
        }
        if heartbeatGap >= historicalPauseMinimum {
            return .mainBlocked
        }
        return .eventAbsence
    }

    @objc(largestGapIn:)
    public static func largestGap(in stamps: [TimeInterval]) -> TimeInterval {
        guard stamps.count >= 2 else { return 0 }
        var widest: TimeInterval = 0
        for index in 1..<stamps.count {
            widest = max(widest, stamps[index] - stamps[index - 1])
        }
        return widest
    }

    /// Pump default and event-tracking modes with a draw tick, a heartbeat
    /// and a background worker. This is the host run-loop, not Horos.app.
    @objc(measureHostRunLoopDuration:)
    public static func measureHostRunLoop(duration: TimeInterval) -> EventCapturePauseSample {
        precondition(Thread.isMainThread, "the run-loop probe has to own the main thread")
        NSApplication.shared.setActivationPolicy(.accessory)

        var draws: [TimeInterval] = []
        var beats: [TimeInterval] = []
        let started = ProcessInfo.processInfo.systemUptime
        let draw = Timer(timeInterval: drawTickInterval, repeats: true) { _ in
            draws.append(ProcessInfo.processInfo.systemUptime)
        }
        let beat = Timer(timeInterval: drawTickInterval, repeats: true) { _ in
            beats.append(ProcessInfo.processInfo.systemUptime)
        }
        for mode in [RunLoop.Mode.default, RunLoop.Mode.eventTracking, RunLoop.Mode.common] {
            RunLoop.current.add(draw, forMode: mode)
            RunLoop.current.add(beat, forMode: mode)
        }

        let counter = IterationCounter()
        let until = started + duration
        DispatchQueue.global(qos: .userInitiated).async {
            var acc: UInt64 = 1
            while ProcessInfo.processInfo.systemUptime < until {
                acc = acc &* 6_364_136_223_846_793_005 &+ 1
                counter.add()
            }
            _ = acc
        }

        let deadline = Date(timeIntervalSinceNow: duration)
        while Date() < deadline {
            RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.016))
            RunLoop.current.run(mode: .eventTracking, before: Date(timeIntervalSinceNow: 0.016))
        }
        draw.invalidate()
        beat.invalidate()

        let elapsed = ProcessInfo.processInfo.systemUptime - started
        let drawGap = largestGap(in: draws)
        let beatGap = largestGap(in: beats)
        return EventCapturePauseSample(
            drawTicks: draws.count,
            heartbeatTicks: beats.count,
            maxDrawGap: drawGap,
            maxHeartbeatGap: beatGap,
            duration: elapsed,
            kind: classify(eventGap: drawGap, heartbeatGap: beatGap),
            backgroundIterations: counter.value
        )
    }
}

private final class IterationCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var count = 0

    func add() {
        lock.lock()
        count += 1
        lock.unlock()
    }

    var value: Int {
        lock.lock()
        defer { lock.unlock() }
        return count
    }
}
