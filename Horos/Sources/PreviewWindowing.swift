import Foundation

/// Where the database preview's window and level came from (#608).
///
/// The browser preview had one pair of numbers and no memory of why they held
/// that value, so it could not tell a default it was free to replace from an
/// adjustment the user had made. Scrolling, a refresh of the same selection and
/// the late arrival of a thumbnail batch all went through the same reset.
///
/// Naming the source separates the three cases the acceptance asks for: the
/// window the file carries, the window computed from the pixels, and the window
/// a person chose.
@objc(HorosPreviewWindowSource)
public enum PreviewWindowSource: Int {
    /// Computed from this frame's intensities.
    case automatic = 0
    /// Window Center/Width as the file stores them.
    case dicom = 1
    /// The range the stored bits can represent, the last resort.
    case storedRange = 2
    /// The range this frame's own values occupy, when there is nothing to
    /// sample: a uniform frame has no percentiles worth taking.
    case frameRange = 5
    /// What the operator set by dragging in the preview.
    case manual = 3
    /// The fixed 0…255 presentation of a colour frame; not a scalar window.
    case color = 4

    public var name: String {
        switch self {
        case .automatic: return "automatic"
        case .dicom: return "DICOM"
        case .storedRange: return "stored range"
        case .frameRange: return "frame range"
        case .manual: return "manual"
        case .color: return "colour"
        }
    }
}

/// One window, with the reason it is the window.
@objc(HorosPreviewWindow)
public final class PreviewWindow: NSObject {
    @objc public let level: Float
    @objc public let width: Float
    @objc public let sourceValue: Int

    public var source: PreviewWindowSource { PreviewWindowSource(rawValue: sourceValue) ?? .automatic }

    @objc(initWithLevel:width:source:)
    public init(level: Float, width: Float, source: PreviewWindowSource) {
        self.level = level
        self.width = width
        self.sourceValue = source.rawValue
        super.init()
    }

    /// A window is usable when both numbers are finite and it covers more than
    /// a single value. A width of zero is a request for automatic selection,
    /// never an image one unit wide.
    @objc public var isValid: Bool {
        level.isFinite && width.isFinite && width > 0
    }

    @objc public var isManual: Bool { source == .manual }

    /// The same numbers, attributed to a person rather than to a computation.
    @objc public var asManual: PreviewWindow {
        PreviewWindow(level: level, width: width, source: .manual)
    }

    public override var description: String {
        String(format: "WL %.4g WW %.4g (%@)", level, width, source.name)
    }

    public override func isEqual(_ object: Any?) -> Bool {
        guard let other = object as? PreviewWindow else { return false }
        return level == other.level && width == other.width && sourceValue == other.sourceValue
    }

    public override var hash: Int {
        var hasher = Hasher()
        hasher.combine(level); hasher.combine(width); hasher.combine(sourceValue)
        return hasher.finalize()
    }
}

/// What the preview is currently showing, and what it may replace (#608).
///
/// The policy owns no pixels and reads no file. It is told which frame is about
/// to be shown — its series, its path and the revision of that path (#603) —
/// and answers two questions: must the defaults be computed again, and which
/// window should be applied. Everything else it remembers.
@objc(HorosPreviewWindowPolicy)
public final class PreviewWindowPolicy: NSObject {
    private struct Identity: Equatable {
        var series: String
        var path: String
        var revision: String
    }

    private var identity: Identity?
    private var manual: PreviewWindow?
    private var applied: PreviewWindow?
    /// The revision each path was last shown at, within the current series.
    /// Cleared on every series change, so it holds one short string per frame
    /// of the series on screen and no more.
    private var revisions: [String: String] = [:]
    /// Incremented whenever the defaults are dropped; a published batch that
    /// carries an older number is stale.
    @objc public private(set) var generation: Int = 0

    /// The adjustment the operator made, while it still applies.
    @objc public var manualWindow: PreviewWindow? { manual }
    /// The window last handed to the view.
    @objc public var appliedWindow: PreviewWindow? { applied }
    /// The series the preview is showing, as the policy knows it.
    @objc public var seriesKey: String? { identity?.series }

    @objc public override init() { super.init() }

    /// Announce the frame the preview is about to show.
    ///
    /// Returns true when the defaults must be computed again: a different
    /// series, the same file at a different revision, or nothing shown yet.
    /// Scrolling inside one series and a second publication of the same frame
    /// both return false, which is what keeps a manual adjustment alive.
    @objc(beginFrameWithSeriesKey:path:revisionKey:)
    @discardableResult
    public func beginFrame(seriesKey: String?, path: String?, revisionKey: String?) -> Bool {
        let candidate = Identity(series: Self.normalize(seriesKey),
                                 path: Self.normalize(path),
                                 revision: Self.normalize(revisionKey))
        guard let current = identity else {
            identity = candidate
            revisions = [candidate.path: candidate.revision]
            manual = nil
            applied = nil
            generation += 1
            return true
        }
        // A series identifier that is present and different is a new series.
        // When either side has none, there is nothing to prove the two frames
        // belong together, so the path decides and a loose file resets.
        let seriesChanged: Bool
        if current.series.isEmpty || candidate.series.isEmpty {
            seriesChanged = current.path != candidate.path || current.series != candidate.series
        } else {
            seriesChanged = current.series != candidate.series
        }
        // The same file, decoded from different bytes, is not the same picture -
        // whether it comes back straight away or after scrolling round the
        // series, which is why the revision is remembered per path (#610).
        var revisionChanged = false
        if let seen = revisions[candidate.path], !seen.isEmpty, !candidate.revision.isEmpty,
           seen != candidate.revision {
            revisionChanged = true
        }
        identity = candidate
        if seriesChanged {
            revisions = [candidate.path: candidate.revision]
        } else {
            revisions[candidate.path] = candidate.revision
        }
        if seriesChanged || revisionChanged || applied == nil {
            manual = nil
            applied = nil
            generation += 1
            return true
        }
        return false
    }

    /// Forget everything; the next frame recomputes its defaults.
    @objc public func reset() {
        identity = nil
        revisions.removeAll()
        manual = nil
        applied = nil
        generation += 1
    }

    /// Record a window the operator asked for.
    ///
    /// A width of zero or a value that is not finite is a request for automatic
    /// selection, not an adjustment: it drops the manual window instead of
    /// storing a degenerate one.
    @objc(recordRequestedLevel:width:)
    @discardableResult
    public func recordRequested(level: Float, width: Float) -> Bool {
        let candidate = PreviewWindow(level: level, width: width, source: .manual)
        guard candidate.isValid else {
            manual = nil
            applied = nil
            return false
        }
        // Re-asserting the window already on screen is not an adjustment. A
        // redraw notification does exactly that, and mistaking it for a person
        // would leave every default labelled as a choice somebody made.
        if let applied, applied.level == level, applied.width == width { return false }
        manual = candidate
        applied = candidate
        return true
    }

    /// The window to hand to the view for this frame.
    ///
    /// A manual adjustment wins while its series is on screen. Otherwise the
    /// ladder is explicit: a colour frame keeps its own presentation, MR takes
    /// the computed window, every other modality keeps a valid DICOM window and
    /// falls back to the computed one, and the stored range is the last resort.
    @objc(windowForModality:dicom:automatic:frameRange:storedRange:isColor:)
    public func window(modality: String?, dicom: PreviewWindow?, automatic: PreviewWindow?,
                       frameRange: PreviewWindow?, storedRange: PreviewWindow?,
                       isColor: Bool) -> PreviewWindow {
        if let manual, manual.isValid, !isColor {
            applied = manual
            return manual
        }
        let resolved = Self.defaultWindow(modality: modality, dicom: dicom, automatic: automatic,
                                          frameRange: frameRange, storedRange: storedRange, isColor: isColor)
        applied = resolved
        return resolved
    }

    /// The ladder on its own, so a test can walk it without a policy instance.
    ///
    /// DICOM or computed first, depending on the modality; then the frame's own
    /// range when there was nothing to compute from; the stored bit range last.
    @objc(defaultWindowForModality:dicom:automatic:frameRange:storedRange:isColor:)
    public static func defaultWindow(modality: String?, dicom: PreviewWindow?, automatic: PreviewWindow?,
                                     frameRange: PreviewWindow?, storedRange: PreviewWindow?,
                                     isColor: Bool) -> PreviewWindow {
        // A colour frame has three samples per pixel and no scalar intensity to
        // window. Imposing one on it is how a photograph turns into a mask.
        if isColor {
            return PreviewWindow(level: 127.5, width: 255, source: .color)
        }
        let code = (modality ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let valid = { (window: PreviewWindow?) -> PreviewWindow? in
            guard let window, window.isValid else { return nil }
            return window
        }
        // MR window values in the wild describe one coil or one vendor's scale;
        // the origin computes them instead. Every other modality carries a
        // window that means something clinically, so it is kept.
        if code == "MR" {
            if let automatic = valid(automatic) { return automatic }
            if let dicom = valid(dicom) { return dicom }
        } else {
            if let dicom = valid(dicom) { return dicom }
            if let automatic = valid(automatic) { return automatic }
        }
        // Nothing to sample - a uniform frame, or one with too few distinct
        // values - still has a minimum and a maximum. They describe this
        // picture; the stored bit range only describes what the file could hold.
        if let frameRange = valid(frameRange) { return frameRange }
        if let storedRange = valid(storedRange) { return storedRange }
        return PreviewWindow(level: 127.5, width: 255, source: .storedRange)
    }

    /// Whether the computed window can matter for this frame, so a caller can
    /// skip sampling the pixels when the ladder would never reach it.
    @objc(needsAutomaticWindowForModality:dicom:isColor:)
    public static func needsAutomaticWindow(modality: String?, dicom: PreviewWindow?, isColor: Bool) -> Bool {
        if isColor { return false }
        let code = (modality ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        if code == "MR" { return true }
        guard let dicom, dicom.isValid else { return true }
        return false
    }

    private static func normalize(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}

/// The window a frame's own intensities suggest (#608).
///
/// Adapted from the sampled, background-rejecting calculation the origin added
/// for MR previews. The workbench decodes into a rescaled float buffer, so
/// there is no slope/intercept step here: the values handed in are already the
/// values the viewer measures. Nothing is written back — the buffer is read
/// through a `const float *` and the quantitative pixels are untouched.
@objc(HorosPreviewAutomaticWindow)
public final class PreviewAutomaticWindow: NSObject {
    /// At most this many samples are examined, whatever the frame's size.
    @objc public static let sampleBudget = 5_000
    /// Below this many usable samples the frame is not worth guessing about.
    @objc public static let minimumSamples = 32

    /// The window for a frame of known shape; the four corners are the
    /// candidates for its background.
    @objc(windowForValues:width:height:modality:)
    public static func window(values: UnsafePointer<Float>?, width: Int, height: Int,
                              modality: String?) -> PreviewWindow? {
        guard let values, width > 0, height > 0 else { return nil }
        let count = width * height
        let buffer = UnsafeBufferPointer(start: values, count: count)
        let corners = [0, width - 1, (height - 1) * width, count - 1]
            .filter { $0 >= 0 && $0 < count }
            .map { buffer[$0] }
            .filter { $0.isFinite }
        return window(buffer: buffer, code: code(modality), background: repeatedValue(in: corners))
    }

    /// The window for a flat run of values, with no shape to take corners from.
    @objc(windowForValues:count:modality:)
    public static func window(values: UnsafePointer<Float>?, count: Int, modality: String?) -> PreviewWindow? {
        guard let values, count > 0 else { return nil }
        let buffer = UnsafeBufferPointer(start: values, count: count)
        let ends = [0, count - 1].map { buffer[$0] }.filter { $0.isFinite }
        return window(buffer: buffer, code: code(modality), background: repeatedValue(in: ends))
    }

    private static func window(buffer: UnsafeBufferPointer<Float>, code: String,
                               background: Float?) -> PreviewWindow? {
        let count = buffer.count
        var samples: [Float] = []
        samples.reserveCapacity(min(count, sampleBudget))
        let step = max(1, count / sampleBudget)
        var index = 0
        while index < count {
            let value = buffer[index]
            index += step
            guard value.isFinite else { continue }
            if let background, abs(value - background) <= tolerance(background) { continue }
            // An MR frame is zero outside the body by construction, which is a
            // background even when the corners disagree.
            if code == "MR" && abs(value) <= Float.ulpOfOne { continue }
            samples.append(value)
        }
        guard samples.count >= minimumSamples else { return nil }
        samples.sort()

        let range: (low: Float, high: Float)
        switch code {
        case "US", "XA", "RF": range = (0.01, 0.99)
        default: range = (0.005, 0.995)
        }
        let lowIndex = percentileIndex(range.low, count: samples.count)
        let highIndex = max(percentileIndex(range.high, count: samples.count), lowIndex)
        var low = samples[lowIndex]
        let high = samples[highIndex]
        // Counts and concentrations start at zero; clipping the low end of a
        // PET or NM frame moves the colour of every quiet voxel.
        if (code == "PT" || code == "NM") && low >= 0 { low = 0 }
        let width = max(high - low, 1)
        let level = low + width * 0.5
        guard width.isFinite, level.isFinite else { return nil }
        return PreviewWindow(level: level, width: width, source: .automatic)
    }

    private static func code(_ modality: String?) -> String {
        (modality ?? "").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    }

    private static func tolerance(_ value: Float) -> Float {
        max(abs(value) * 0.00001, 0.0001)
    }

    private static func repeatedValue(in values: [Float]) -> Float? {
        guard values.count >= 2 else { return nil }
        var best: Float?
        var bestCount = 1
        for candidate in values {
            let limit = tolerance(candidate)
            let count = values.reduce(into: 0) { total, value in
                if abs(value - candidate) <= limit { total += 1 }
            }
            if count > bestCount {
                best = candidate
                bestCount = count
            }
        }
        return best
    }

    private static func percentileIndex(_ percentile: Float, count: Int) -> Int {
        guard count > 1 else { return 0 }
        let clamped = min(max(percentile, 0), 1)
        return min(max(Int((Float(count - 1) * clamped).rounded()), 0), count - 1)
    }
}

/// One redraw per burst of preview requests (#608).
///
/// A scroll wheel delivers a tick per notch; each one used to decode a frame
/// before the next arrived. The coalescer keeps only the latest request, runs
/// it on the main run loop after a bounded delay, and guarantees that the last
/// position asked for is the one that is drawn. It holds one pending item, so
/// the work and the memory are bounded whatever the wheel does.
@objc(HorosPreviewRedrawCoalescer)
public final class PreviewRedrawCoalescer: NSObject {
    private let interval: TimeInterval
    private var pendingWork: (() -> Void)?
    private var scheduled = false
    private var burstStartedAt: TimeInterval = 0
    /// How many requests were folded into a redraw that had not run yet.
    @objc public private(set) var coalescedCount: Int = 0
    /// How many redraws actually ran.
    @objc public private(set) var redrawCount: Int = 0
    /// Whether a redraw is waiting to run.
    @objc public var hasPendingRedraw: Bool { pendingWork != nil }

    @objc(initWithInterval:)
    public init(interval: TimeInterval) {
        self.interval = interval.isFinite && interval > 0 ? min(interval, 0.5) : 0.03
        super.init()
    }

    @objc public convenience override init() { self.init(interval: 0.03) }

    /// Ask for a redraw. Only one request survives: the newest replaces the
    /// one still waiting, so a burst of wheel notches costs one decode.
    @objc(requestRedraw:)
    public func request(_ work: @escaping () -> Void) {
        if pendingWork != nil { coalescedCount += 1 }
        pendingWork = work
        guard !scheduled else { return }
        scheduled = true
        burstStartedAt = ProcessInfo.processInfo.systemUptime
        DispatchQueue.main.asyncAfter(deadline: .now() + interval) { [weak self] in
            self?.run()
        }
    }

    /// Run the waiting redraw now; the end of a gesture must not wait.
    @objc public func flush() {
        run()
    }

    @objc public func cancel() {
        pendingWork = nil
        scheduled = false
    }

    @objc public func resetCounters() {
        coalescedCount = 0
        redrawCount = 0
    }

    private func run() {
        scheduled = false
        guard let work = pendingWork else { return }
        pendingWork = nil
        redrawCount += 1
        work()
    }
}
