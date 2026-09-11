import Foundation

/// One methodology for 3D interaction timing, shared by VTK today and Metal later.
///
/// #210 needs a baseline that #375/#385 can repeat: the same volume, camera,
/// quality and events, with render time kept apart from load, preset generation
/// and input. A single stopwatch cannot say which of those spent the frame, and
/// a Metal rewrite that times something else cannot be compared to this host.
///
/// So the protocol is fixed here - the CT phantom already used by the 3D preset
/// panel, a known viewport and clip slab, rotate/pan/clip samples, first frame
/// as its own event - and the report writes p50/p95 or "not measured". Empty is
/// not zero. Nothing here changes how VTK draws.
@objc(HorosVRInteractionBenchmark)
public final class VRInteractionBenchmark: NSObject {

    @objc public static let protocolID = "horos-vr-interaction-210"
    @objc public static let datasetGenerator = "tools/generate-ct-phantom-fixture.py"
    @objc public static let datasetSlices = 200
    @objc public static let datasetSize = 256
    @objc public static let datasetSpacingMM = 1.0
    @objc public static let datasetPatientID = "CT-PHANTOM-34"
    @objc public static let viewportWidth = 1024
    @objc public static let viewportHeight = 768
    @objc public static let cameraProjection = "parallel"
    @objc public static let qualityName = "shipped-LOD"
    @objc public static let clipThicknessMM = 40.0

    @objc public static var current: VRInteractionBenchmark?

    @objc public let revision: String
    @objc public let os: String
    @objc public let architecture: String
    @objc public let gpu: String
    @objc public let scale: Double

    private struct Phase {
        let name: String
        var milliseconds: Double
    }

    private var phases: [Phase] = []
    private var phaseStarted: [String: TimeInterval] = [:]
    private var samples: [String: [Double]] = [:]
    private var sampleStarted: (name: String, at: TimeInterval)?
    private var firstFrameMs: Double?
    private var lastMemoryBytes: UInt64 = 0
    private var lastCPUPercent: Double?
    private var lastGPUPercent: Double?
    private var stacks: String?

    @objc public init(revision: String, os: String, architecture: String, gpu: String, scale: Double) {
        self.revision = revision
        self.os = os
        self.architecture = architecture
        self.gpu = gpu
        self.scale = scale
    }

    @objc(startSessionRevision:os:architecture:gpu:scale:)
    public static func startSession(revision: String, os: String, architecture: String, gpu: String, scale: Double) -> VRInteractionBenchmark {
        let session = VRInteractionBenchmark(revision: revision, os: os, architecture: architecture, gpu: gpu, scale: scale)
        current = session
        return session
    }

    @objc public static func stopSession() {
        current = nil
    }

    @objc public static func beginSample(_ name: String) {
        current?.beginNamedSample(name)
    }

    @objc public static func endSample() {
        current?.finishSample()
    }

    @objc public static func noteFirstFrame() {
        current?.markFirstFrame()
    }

    @objc public func beginPhase(_ name: String) {
        if phaseStarted[name] == nil {
            phaseStarted[name] = Date.timeIntervalSinceReferenceDate
        }
    }

    @objc public func endPhase(_ name: String) {
        guard let from = phaseStarted.removeValue(forKey: name) else { return }
        let ms = (Date.timeIntervalSinceReferenceDate - from) * 1000
        if let index = phases.firstIndex(where: { $0.name == name }) {
            phases[index].milliseconds += ms
        } else {
            phases.append(Phase(name: name, milliseconds: ms))
        }
    }

    @objc(recordSample:milliseconds:cpuPercent:gpuPercent:memoryBytes:)
    public func recordSample(_ name: String, milliseconds: Double, cpuPercent: Double, gpuPercent: Double, memoryBytes: UInt64) {
        samples[name, default: []].append(milliseconds)
        if name == "firstFrame", firstFrameMs == nil {
            firstFrameMs = milliseconds
        }
        lastMemoryBytes = memoryBytes
        if cpuPercent >= 0 { lastCPUPercent = cpuPercent }
        if gpuPercent >= 0 { lastGPUPercent = gpuPercent }
    }

    @objc public func recordStacks(_ text: String) {
        stacks = text
    }

    /// Linear interpolation on the sorted samples. An empty series is not a
    /// number: the report has to say the event was not measured.
    @objc(percentile:p:)
    public static func percentile(_ values: [NSNumber], p: Double) -> NSNumber? {
        let samples = values.map { $0.doubleValue }
        guard let value = interpolatedPercentile(samples, p: p) else { return nil }
        return NSNumber(value: value)
    }

    @objc(kindForName:)
    public static func kind(for name: String) -> String {
        switch name {
        case "rotate", "pan", "clip", "firstFrame":
            return "interaction"
        case "load", "preset", "input":
            return "setup"
        default:
            return "other"
        }
    }

    @objc public var summary: String {
        let rotate = interactionLine("rotate")
        let pan = interactionLine("pan")
        let clip = interactionLine("clip")
        let first = firstFrameMs.map { Self.format($0) } ?? "not measured"
        return "\(Self.protocolID): first frame \(first); rotate \(rotate); pan \(pan); clip \(clip)"
    }

    @objc public var reportJSON: String {
        let payload: [String: Any] = [
            "protocol": Self.protocolID,
            "etapa": "A",
            "revision": revision,
            "os": os,
            "architecture": architecture,
            "gpu": gpu,
            "scale": scale,
            "dataset": [
                "generator": Self.datasetGenerator,
                "slices": Self.datasetSlices,
                "size": Self.datasetSize,
                "spacingMM": Self.datasetSpacingMM,
                "patientID": Self.datasetPatientID,
            ],
            "configuration": [
                "viewport": [Self.viewportWidth, Self.viewportHeight],
                "projection": Self.cameraProjection,
                "quality": Self.qualityName,
                "clipThicknessMM": Self.clipThicknessMM,
            ],
            "phases": Dictionary(uniqueKeysWithValues: phases.map { ($0.name, $0.milliseconds) }),
            "interactions": [
                "rotate": interactionPayload("rotate"),
                "pan": interactionPayload("pan"),
                "clip": interactionPayload("clip"),
            ],
            "firstFrameMs": firstFrameMs ?? NSNull(),
            "cpuPercent": lastCPUPercent ?? NSNull(),
            "gpuPercent": lastGPUPercent ?? NSNull(),
            "memoryBytes": lastMemoryBytes,
            "stacks": stacks ?? "not captured",
            "optimization": "none",
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]),
              let text = String(data: data, encoding: .utf8) else {
            return "{}"
        }
        return text
    }

    private func beginNamedSample(_ name: String) {
        if sampleStarted == nil {
            sampleStarted = (name, Date.timeIntervalSinceReferenceDate)
        }
    }

    private func finishSample() {
        guard let running = sampleStarted else { return }
        sampleStarted = nil
        let ms = (Date.timeIntervalSinceReferenceDate - running.at) * 1000
        samples[running.name, default: []].append(ms)
        if running.name == "firstFrame", firstFrameMs == nil {
            firstFrameMs = ms
        }
        lastMemoryBytes = Self.residentMemoryBytes()
    }

    private func markFirstFrame() {
        guard firstFrameMs == nil else { return }
        if let running = sampleStarted {
            firstFrameMs = (Date.timeIntervalSinceReferenceDate - running.at) * 1000
            sampleStarted = nil
        }
    }

    private func interactionLine(_ name: String) -> String {
        let values = samples[name] ?? []
        guard let p50 = Self.interpolatedPercentile(values, p: 50),
              let p95 = Self.interpolatedPercentile(values, p: 95) else {
            return "not measured"
        }
        return "n=\(values.count) p50 \(Self.format(p50)) p95 \(Self.format(p95))"
    }

    private func interactionPayload(_ name: String) -> [String: Any] {
        let values = samples[name] ?? []
        return [
            "n": values.count,
            "p50": Self.interpolatedPercentile(values, p: 50) ?? NSNull(),
            "p95": Self.interpolatedPercentile(values, p: 95) ?? NSNull(),
        ]
    }

    static func interpolatedPercentile(_ values: [Double], p: Double) -> Double? {
        guard values.isEmpty == false, p >= 0, p <= 100 else { return nil }
        let sorted = values.sorted()
        if sorted.count == 1 { return sorted[0] }
        let rank = (p / 100.0) * Double(sorted.count - 1)
        let low = Int(rank.rounded(.down))
        let high = Int(rank.rounded(.up))
        if low == high { return sorted[low] }
        let weight = rank - Double(low)
        return sorted[low] * (1 - weight) + sorted[high] * weight
    }

    static func format(_ milliseconds: Double) -> String {
        if milliseconds >= 1000 { return String(format: "%.2f s", milliseconds / 1000) }
        if milliseconds >= 1 { return String(format: "%.1f ms", milliseconds) }
        return String(format: "%.0f µs", milliseconds * 1000)
    }

    static func residentMemoryBytes() -> UInt64 {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
        let result = withUnsafeMutablePointer(to: &info) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        return result == KERN_SUCCESS ? UInt64(info.resident_size) : 0
    }
}
