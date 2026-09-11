import Foundation

/// How long a medium took to import, phase by phase.
///
/// "Minutes per image" is the report, and a single elapsed time cannot say which
/// part of the import spent them. Reading a disc is four different things:
/// listing what is on it, reading its index, opening every file to find out
/// whether it is DICOM, and then parsing and indexing the ones that are - and
/// after that, copying them into the database. Each is capable of being the slow
/// one, and they are slow for different reasons.
///
/// So they are timed apart and reported together, in one line, with the counts
/// that make the durations comparable between one disc and another.
@objc(HorosMediaScanTiming)
public final class MediaScanTiming: NSObject {

    /// A phase's name, how long it took, and what it worked on.
    private struct Phase {
        let name: String
        let seconds: TimeInterval
        let count: Int?
        let noun: String?
    }

    @objc public let medium: String
    private var phases: [Phase] = []
    private var started: [String: TimeInterval] = [:]

    @objc public init(medium: String) {
        self.medium = medium
    }

    /// Start timing a phase. A phase already running is left as it is.
    @objc public func begin(_ name: String) {
        if started[name] == nil {
            started[name] = Date.timeIntervalSinceReferenceDate
        }
    }

    /// Stop timing a phase and record what it worked on. A phase that was never
    /// begun is ignored, so a scan that skips a phase does not report it as
    /// having taken no time.
    @objc public func end(_ name: String, count: Int, noun: String) {
        guard let from = started.removeValue(forKey: name) else { return }
        phases.append(Phase(name: name, seconds: Date.timeIntervalSinceReferenceDate - from,
                            count: count, noun: noun))
    }

    /// The same, for a phase whose work is not counted in anything.
    @objc public func end(_ name: String) {
        guard let from = started.removeValue(forKey: name) else { return }
        phases.append(Phase(name: name, seconds: Date.timeIntervalSinceReferenceDate - from,
                            count: nil, noun: nil))
    }

    /// Everything that was timed, added up.
    @objc public var total: TimeInterval {
        return phases.reduce(0) { $0 + $1.seconds }
    }

    /// Internal rather than private so a driver compiled alongside it can ask for
    /// durations this test cannot afford to wait out.
    static func duration(_ seconds: TimeInterval) -> String {
        if seconds >= 60 {
            let minutes = Int(seconds / 60)
            return String(format: "%d min %.0f s", minutes, seconds - Double(minutes) * 60)
        }
        if seconds >= 1 { return String(format: "%.1f s", seconds) }
        return String(format: "%.0f ms", seconds * 1000)
    }

    /// One line naming every phase, longest first, and what each of them was for.
    ///
    /// The order is by duration rather than by when they ran: someone reading
    /// this wants to know where the time went, and the first phrase after the
    /// total answers that.
    @objc public var summary: String {
        guard phases.isEmpty == false else {
            return "\(medium): nothing was timed"
        }
        let ordered = phases.sorted { $0.seconds > $1.seconds }
        let parts = ordered.map { phase -> String in
            guard let count = phase.count, let noun = phase.noun else {
                return "\(MediaScanTiming.duration(phase.seconds)) \(phase.name)"
            }
            let plural = count == 1 ? noun : noun + "s"
            return "\(MediaScanTiming.duration(phase.seconds)) \(phase.name) \(count) \(plural)"
        }
        return "\(medium): \(MediaScanTiming.duration(total)) in all - " + parts.joined(separator: ", ")
    }

    /// What one instance cost, over the phases that had to touch every one of
    /// them. Empty when nothing was imported, because a rate per nothing is not
    /// a rate.
    @objc public func perInstance(_ instances: Int) -> String {
        guard instances > 0 else { return "" }
        return "\(MediaScanTiming.duration(total / Double(instances))) per instance"
    }
}
