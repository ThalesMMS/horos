import Foundation
import Metal
import QuartzCore
import os

/// Where the time of a Metal operation goes (#619).
///
/// Off unless the `HorosMetalPerformanceTrace` default is YES when the process
/// starts (`-HorosMetalPerformanceTrace YES`); it is read once. Off, every entry
/// point returns after one comparison and nothing is timed, kept or logged.
///
/// On, each operation leaves one sample - an operation name and durations, never
/// a patient, study, series or file name - in a buffer of the last 4096, readable
/// with `snapshot()`, and one `MetalOperation` signpost event for Instruments.
/// Timing adds no command buffer, completion handler or wait: host times are read
/// around what the operation already does, and GPU times from the command buffer
/// after the wait the operation already makes. The extra fields of a sample are
/// built only when it is kept.
///
/// Fields, in milliseconds, each absent (`NSNull` in a snapshot) when the moment
/// it needs was not observed - never reported as zero:
///
/// - `cpu_prepare_ms`: from the start of the operation to the commit (encoding,
///   buffers, tables; for a host operation, all of it)
/// - `submit_to_gpu_ms`: commit to the GPU starting the command buffer
///   (`gpuStartTime`, which Metal leaves at 0 when it has none)
/// - `gpu_ms`: `gpuEndTime - gpuStartTime`
/// - `wait_ms`: the caller blocked in `waitUntilCompleted`, commit to its return
/// - `gpu_to_observed_ms`: the GPU finishing to the caller seeing it
/// - `readback_ms`: after the wait, copying results out (`Data`, host buffers)
/// - `total_ms`: start to the end of the operation
///
/// Operations: `mpr.pipeline`, `vr.pipeline`, `planar.pipeline` (library and
/// pipeline creation; `cold` says whether it compiled), `mpr.upload`, `vr.upload`
/// (volume to the GPU), `mpr.reslice`, `vr.render`, `planar.metal3.render`,
/// `planar.metal4.render`, and the host's own share: `mpr.host_prepare`,
/// `vr.host_snapshot`, `vr.host_convert`. Since #620 the MPR plane is copied once,
/// into the host's image, within `mpr.reslice`'s readback; there is no `mpr.host_copy`.
@objc(HorosMetalPerformanceTrace)
public final class MetalPerformanceTrace: NSObject {
    @objc public static let enabled = UserDefaults.standard.bool(forKey: "HorosMetalPerformanceTrace")

    private static let log = OSLog(subsystem: Bundle.main.bundleIdentifier ?? "org.horosproject.horos",
                                   category: "MetalPerformance")
    private static let lock = NSLock()
    private static var samples: [[String: Any]] = []
    private static var dropped = 0
    static let capacity = 4096

    /// The host time now, or nil when the trace is off: an operation keeps what
    /// this returns and hands it back, and a nil start records nothing.
    public static func now() -> CFTimeInterval? {
        enabled ? CACurrentMediaTime() : nil
    }

    /// For Objective-C: the host time now, or NaN when the trace is off.
    @objc(now) public static func hostTime() -> Double {
        enabled ? CACurrentMediaTime() : .nan
    }

    /// An operation that ran one command buffer and waited for it.
    ///
    /// `committedAt` is taken just before `commit()`, `completedAt` just after
    /// `waitUntilCompleted()` returns, `finishedAt` after the results are copied out.
    public static func record(_ operation: String, startedAt: CFTimeInterval?, committedAt: CFTimeInterval?,
                              completedAt: CFTimeInterval?, command: MTLCommandBuffer?,
                              finishedAt: CFTimeInterval? = nil, extra: @autoclosure () -> [String: Any] = [:]) {
        guard enabled, let startedAt else { return }
        var gpuStart: CFTimeInterval?, gpuEnd: CFTimeInterval?
        if let command, command.status == .completed, command.gpuStartTime > 0, command.gpuEndTime >= command.gpuStartTime {
            gpuStart = command.gpuStartTime
            gpuEnd = command.gpuEndTime
        }
        var fields = extra()
        fields["status"] = command.map { $0.status == .completed ? "completed" : "failed" } ?? "none"
        store(operation, fields: fields, startedAt: startedAt, committedAt: committedAt, gpuStart: gpuStart,
              gpuEnd: gpuEnd, completedAt: completedAt, finishedAt: finishedAt, waited: true)
    }

    /// A Metal 4 submission observed through its commit feedback: GPU times from
    /// the feedback, `completedAt` when the feedback was delivered. No wait is
    /// implied (`wait_ms` is absent).
    public static func record(_ operation: String, startedAt: CFTimeInterval?, committedAt: CFTimeInterval?,
                              observedAt: CFTimeInterval?, gpuStartTime: CFTimeInterval, gpuEndTime: CFTimeInterval,
                              failed: Bool, extra: @autoclosure () -> [String: Any] = [:]) {
        guard enabled, let startedAt else { return }
        let valid = !failed && gpuStartTime > 0 && gpuEndTime >= gpuStartTime
        var fields = extra()
        fields["status"] = failed ? "failed" : "completed"
        store(operation, fields: fields, startedAt: startedAt, committedAt: committedAt,
              gpuStart: valid ? gpuStartTime : nil, gpuEnd: valid ? gpuEndTime : nil,
              completedAt: observedAt, finishedAt: nil, waited: false)
    }

    /// A Metal 4 submission its caller waited for (#623): GPU times from the commit
    /// feedback, `completedAt` when the waiting caller resumed, `finishedAt` after the
    /// results are copied out.
    public static func record(_ operation: String, startedAt: CFTimeInterval?, committedAt: CFTimeInterval?,
                              completedAt: CFTimeInterval?, gpuStartTime: CFTimeInterval, gpuEndTime: CFTimeInterval,
                              failed: Bool, finishedAt: CFTimeInterval?, extra: @autoclosure () -> [String: Any] = [:]) {
        guard enabled, let startedAt else { return }
        let valid = !failed && gpuStartTime > 0 && gpuEndTime >= gpuStartTime
        var fields = extra()
        fields["status"] = failed ? "failed" : "completed"
        store(operation, fields: fields, startedAt: startedAt, committedAt: committedAt,
              gpuStart: valid ? gpuStartTime : nil, gpuEnd: valid ? gpuEndTime : nil,
              completedAt: completedAt, finishedAt: finishedAt, waited: true)
    }

    /// Work without a command buffer: a pipeline built, a texture filled, the
    /// host preparing or converting.
    public static func record(_ operation: String, startedAt: CFTimeInterval?,
                              extra: @autoclosure () -> [String: Any] = [:]) {
        guard enabled, let startedAt else { return }
        let end = CACurrentMediaTime()
        store(operation, fields: extra(), startedAt: startedAt, committedAt: end, gpuStart: nil, gpuEnd: nil,
              completedAt: nil, finishedAt: end, waited: false)
    }

    /// For Objective-C: host work that began at `startedAt` (from `now`) and ends now.
    @objc(recordHostOperation:startedAt:)
    public static func recordHost(_ operation: String, startedAt: Double) {
        guard enabled, startedAt.isFinite else { return }
        record(operation, startedAt: startedAt)
    }

    /// Every sample kept, oldest first, and how many older ones the buffer dropped.
    @objc public static func snapshot() -> [String: Any] {
        lock.lock(); defer { lock.unlock() }
        return ["enabled": enabled, "dropped": dropped, "samples": samples]
    }

    @objc public static func reset() {
        lock.lock(); samples.removeAll(); dropped = 0; lock.unlock()
    }

    private static func milliseconds(_ from: CFTimeInterval?, _ to: CFTimeInterval?) -> Any {
        guard let from, let to, to >= from, (to - from).isFinite else { return NSNull() }
        return (to - from) * 1000
    }

    private static func store(_ operation: String, fields: [String: Any], startedAt: CFTimeInterval,
                              committedAt: CFTimeInterval?, gpuStart: CFTimeInterval?, gpuEnd: CFTimeInterval?,
                              completedAt: CFTimeInterval?, finishedAt: CFTimeInterval?, waited: Bool) {
        var sample = fields
        sample["operation"] = operation
        sample["cpu_prepare_ms"] = milliseconds(startedAt, committedAt)
        sample["submit_to_gpu_ms"] = milliseconds(committedAt, gpuStart)
        sample["gpu_ms"] = milliseconds(gpuStart, gpuEnd)
        sample["wait_ms"] = waited ? milliseconds(committedAt, completedAt) : NSNull()
        sample["gpu_to_observed_ms"] = milliseconds(gpuEnd, completedAt)
        sample["readback_ms"] = milliseconds(completedAt, finishedAt)
        let end = finishedAt ?? completedAt ?? committedAt
        sample["total_ms"] = milliseconds(startedAt, end)
        lock.lock()
        if samples.count == capacity {
            samples.removeFirst()
            dropped += 1
        }
        samples.append(sample)
        lock.unlock()
        let total = (sample["total_ms"] as? Double) ?? -1, gpu = (sample["gpu_ms"] as? Double) ?? -1
        os_signpost(.event, log: log, name: "MetalOperation", "%{public}s total_ms=%.3f gpu_ms=%.3f",
                    operation, total, gpu)
    }
}
