import AppKit

/// Cell-backed slider for Viewer.xib. On macOS 26, stock `NSSlider` decodes
/// into a SwiftUI `_NSCoreHostingView` (`SliderWrapper`) backed by
/// `NSSliderAquaduckVisualProvider`. That AttributeGraph table grows on
/// `initWithCoder` (`loadWindow` → slider decode → `AG::data::table::grow_region`)
/// and does not shrink when the viewer closes.
///
/// The cell keeps the value contract (`doubleValue`, `minValue`, tick marks) so
/// every outlet in `ViewerController` still works, but the cell does not draw
/// or track on macOS 26 without its visual provider. The view therefore draws
/// the slider itself, in the current AppKit idiom (capsule track, accent fill,
/// round knob), and tracks the mouse itself.
@objc(HorosCellSliderCell)
public final class HorosCellSliderCell: NSSliderCell {
    @objc public var usesAquaduck: Bool {
        get { false }
        set {}
    }

    @objc func _visualProvider() -> AnyObject? { nil }
    @objc func _visualProviderIfExists() -> AnyObject? { nil }
    @objc func _visualProviderInView(_ view: Any?) -> AnyObject? { nil }
}

@objc(HorosCellSlider)
public class HorosCellSlider: NSSlider {
    public override static var cellClass: AnyClass? {
        get { HorosCellSliderCell.self }
        set {}
    }

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        adoptCellDrawnPath()
    }

    public required init?(coder: NSCoder) {
        super.init(coder: coder)
        adoptCellDrawnPath()
    }

    private func adoptCellDrawnPath() {
        guard !(cell is HorosCellSliderCell) else { return }
        let next = HorosCellSliderCell()
        if let old = cell as? NSSliderCell {
            next.minValue = old.minValue
            next.maxValue = old.maxValue
            next.doubleValue = old.doubleValue
            next.numberOfTickMarks = old.numberOfTickMarks
            next.allowsTickMarkValuesOnly = old.allowsTickMarkValuesOnly
            next.tickMarkPosition = old.tickMarkPosition
            next.sliderType = old.sliderType
            next.controlSize = old.controlSize
            next.isContinuous = old.isContinuous
            next.isEnabled = old.isEnabled
            next.tag = old.tag
        }
        cell = next
    }

    // MARK: - SwiftUI host suppression

    public override func layout() {
        // Skip NSSlider.layout, which installs SliderWrapper hosts.
    }

    @objc func _layoutComponentSubviewsIfNecessary() {}
    @objc func _updateComponentSubviewRenderingState() {}
    @objc func _clearComponentSubviews() {}

    public override var wantsUpdateLayer: Bool { false }

    // MARK: - Value contract

    public override var doubleValue: Double {
        get { super.doubleValue }
        set { super.doubleValue = newValue; valueDidChange() }
    }

    public override var floatValue: Float {
        get { super.floatValue }
        set { super.floatValue = newValue; valueDidChange() }
    }

    public override var intValue: Int32 {
        get { super.intValue }
        set { super.intValue = newValue; valueDidChange() }
    }

    public override var integerValue: Int {
        get { super.integerValue }
        set { super.integerValue = newValue; valueDidChange() }
    }

    public override var minValue: Double {
        get { super.minValue }
        set { super.minValue = newValue; needsDisplay = true }
    }

    public override var maxValue: Double {
        get { super.maxValue }
        set { super.maxValue = newValue; needsDisplay = true }
    }

    public override var numberOfTickMarks: Int {
        get { super.numberOfTickMarks }
        set { super.numberOfTickMarks = newValue; needsDisplay = true }
    }

    public override var isEnabled: Bool {
        get { super.isEnabled }
        set { super.isEnabled = newValue; needsDisplay = true }
    }

    /// Subclasses that record values (the image navigation bar) hook here.
    @objc public func valueDidChange() {
        needsDisplay = true
    }

    /// Position of `doubleValue` between `minValue` and `maxValue`, in 0…1.
    @objc public var fraction: CGFloat {
        let span = maxValue - minValue
        guard span > 0 else { return 0 }
        return CGFloat(min(1, max(0, (doubleValue - minValue) / span)))
    }

    /// Snaps to tick marks when the cell only allows tick values. The cell's
    /// own `closestTickMarkValue` relies on the visual provider on macOS 26.
    @objc public func snappedValue(_ value: Double) -> Double {
        let clamped = min(maxValue, max(minValue, value))
        guard allowsTickMarkValuesOnly, numberOfTickMarks > 1, maxValue > minValue else { return clamped }
        let step = (maxValue - minValue) / Double(numberOfTickMarks - 1)
        return minValue + (((clamped - minValue) / step).rounded()) * step
    }

    // MARK: - Geometry

    @objc public var isHorizontalSlider: Bool { bounds.width >= bounds.height }

    @objc public var knobDiameter: CGFloat {
        switch controlSize {
        case .mini: return 11
        case .small: return 13
        default: return 16
        }
    }

    @objc public var trackThickness: CGFloat {
        controlSize == .regular ? 5 : 4
    }

    /// The span the knob centre travels, inset by the knob radius.
    @objc public var trackRect: NSRect {
        let radius = knobDiameter / 2
        if isHorizontalSlider {
            return NSRect(x: bounds.minX + radius,
                          y: bounds.midY - trackThickness / 2,
                          width: max(0, bounds.width - knobDiameter),
                          height: trackThickness)
        }
        return NSRect(x: bounds.midX - trackThickness / 2,
                      y: bounds.minY + radius,
                      width: trackThickness,
                      height: max(0, bounds.height - knobDiameter))
    }

    @objc public var knobCenter: NSPoint {
        let track = trackRect
        if isHorizontalSlider {
            return NSPoint(x: track.minX + track.width * fraction, y: bounds.midY)
        }
        return NSPoint(x: bounds.midX, y: track.minY + track.height * fraction)
    }

    /// Value for a point in view coordinates. Subclasses with their own layout
    /// override this together with `draw`.
    @objc public func value(at point: NSPoint) -> Double {
        let track = trackRect
        let t: CGFloat
        if isHorizontalSlider {
            t = track.width > 0 ? (point.x - track.minX) / track.width : 0
        } else {
            t = track.height > 0 ? (point.y - track.minY) / track.height : 0
        }
        let raw = minValue + Double(min(1, max(0, t))) * (maxValue - minValue)
        return snappedValue(raw)
    }

    // MARK: - Drawing

    public override func draw(_ dirtyRect: NSRect) {
        let enabled = isEnabled
        let alpha: CGFloat = enabled ? 1 : 0.45
        let track = trackRect
        let radius = trackThickness / 2

        NSGraphicsContext.saveGraphicsState()
        defer { NSGraphicsContext.restoreGraphicsState() }

        NSColor.tertiaryLabelColor.withAlphaComponent(0.28 * alpha).setFill()
        NSBezierPath(roundedRect: track, xRadius: radius, yRadius: radius).fill()

        var filled = track
        if isHorizontalSlider {
            filled.size.width = track.width * fraction
        } else {
            filled.size.height = track.height * fraction
        }
        if !filled.isEmpty {
            NSColor.controlAccentColor.withAlphaComponent(alpha).setFill()
            NSBezierPath(roundedRect: filled, xRadius: radius, yRadius: radius).fill()
        }

        drawTickMarks(along: track, alpha: alpha)
        drawKnob(at: knobCenter, alpha: alpha)
    }

    private func drawTickMarks(along track: NSRect, alpha: CGFloat) {
        let count = numberOfTickMarks
        guard count >= 2, count <= 50 else { return }
        NSColor.tertiaryLabelColor.withAlphaComponent(0.6 * alpha).setFill()
        let gap: CGFloat = 3
        for index in 0..<count {
            let t = CGFloat(index) / CGFloat(count - 1)
            if isHorizontalSlider {
                let x = track.minX + track.width * t
                let y = tickMarkPosition == .above ? track.maxY + gap : track.minY - gap - 3
                NSRect(x: x - 0.5, y: y, width: 1, height: 3).fill()
            } else {
                let y = track.minY + track.height * t
                let x = tickMarkPosition == .trailing ? track.maxX + gap : track.minX - gap - 3
                NSRect(x: x, y: y - 0.5, width: 3, height: 1).fill()
            }
        }
    }

    private func drawKnob(at center: NSPoint, alpha: CGFloat) {
        let diameter = knobDiameter
        let rect = NSRect(x: center.x - diameter / 2, y: center.y - diameter / 2, width: diameter, height: diameter)
        let path = NSBezierPath(ovalIn: rect)

        NSGraphicsContext.saveGraphicsState()
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.25 * alpha)
        shadow.shadowBlurRadius = 2
        shadow.shadowOffset = NSSize(width: 0, height: -0.5)
        shadow.set()
        let isDark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        (isDark ? NSColor(white: 0.85, alpha: alpha) : NSColor(white: 1, alpha: alpha)).setFill()
        path.fill()
        NSGraphicsContext.restoreGraphicsState()

        NSColor.black.withAlphaComponent(0.18 * alpha).setStroke()
        path.lineWidth = 0.5
        path.stroke()
    }

    // MARK: - Tracking

    /// The toolbar panel is never the key window; the first click must act.
    public override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    public override func mouseDown(with event: NSEvent) {
        guard isEnabled, let window else { return }
        apply(event: event)
        var finished = false
        while !finished {
            guard let next = window.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]) else { break }
            switch next.type {
            case .leftMouseDragged:
                apply(event: next)
            default:
                finished = true
            }
        }
        if !isContinuous {
            sendAction(action, to: target)
        }
    }

    private func apply(event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let next = value(at: point)
        guard next != doubleValue else { return }
        doubleValue = next
        if isContinuous {
            sendAction(action, to: target)
        }
    }
}
