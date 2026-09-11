import AppKit

/// The strip above the 2D viewport. It is the `slider` outlet of
/// `ViewerController`, so it keeps the `NSSlider` contract the controller and
/// `DCMView.sliderAction:` use: `intValue` is the image index (already
/// inverted by the controller when the data is flipped), `maxValue` is the last
/// index and `numberOfTickMarks` is the image count.
///
/// On top of that contract it remembers which indices were displayed since the
/// series was loaded, and draws them as a filled band, with the current image
/// as a marker. Loading a series resets the band because the controller sets
/// the tick count on every load.
@objc(HorosImageNavigationSlider)
public final class ImageNavigationSlider: HorosCellSlider {
    private var visited = IndexSet()

    @objc public var visitedIndexes: IndexSet { visited }

    @objc public var imageCount: Int {
        if numberOfTickMarks > 0 { return numberOfTickMarks }
        return max(1, Int((maxValue - minValue).rounded()) + 1)
    }

    @objc public func resetVisitedImages() {
        visited.removeAll()
        needsDisplay = true
    }

    public override var numberOfTickMarks: Int {
        get { super.numberOfTickMarks }
        set {
            super.numberOfTickMarks = newValue
            resetVisitedImages()
        }
    }

    public override func valueDidChange() {
        let index = Int(doubleValue.rounded())
        if index >= 0, index < imageCount {
            visited.insert(index)
        }
        needsDisplay = true
    }

    // MARK: - Geometry

    private var barInset: CGFloat { 1 }
    private var barHeight: CGFloat { 6 }

    private var barRect: NSRect {
        NSRect(x: bounds.minX + barInset,
               y: bounds.midY - barHeight / 2,
               width: max(0, bounds.width - 2 * barInset),
               height: barHeight)
    }

    private func x(forIndex index: Int) -> CGFloat {
        let bar = barRect
        return bar.minX + bar.width * CGFloat(index) / CGFloat(imageCount)
    }

    public override func value(at point: NSPoint) -> Double {
        let bar = barRect
        guard bar.width > 0 else { return minValue }
        let t = min(1, max(0, (point.x - bar.minX) / bar.width))
        let index = min(imageCount - 1, Int(t * CGFloat(imageCount)))
        return snappedValue(minValue + Double(index))
    }

    // MARK: - Drawing

    public override func draw(_ dirtyRect: NSRect) {
        let alpha: CGFloat = isEnabled ? 1 : 0.45
        let bar = barRect
        let radius = bar.height / 2

        NSGraphicsContext.saveGraphicsState()
        defer { NSGraphicsContext.restoreGraphicsState() }

        NSColor.labelColor.withAlphaComponent(0.16 * alpha).setFill()
        NSBezierPath(roundedRect: bar, xRadius: radius, yRadius: radius).fill()

        if imageCount > 1 {
            NSBezierPath(roundedRect: bar, xRadius: radius, yRadius: radius).addClip()
            NSColor.controlAccentColor.withAlphaComponent(0.7 * alpha).setFill()
            for range in visited.rangeView {
                let start = x(forIndex: range.lowerBound)
                let end = x(forIndex: range.upperBound)
                NSRect(x: start, y: bar.minY, width: max(1, end - start), height: bar.height).fill()
            }
        }

        let index = Int(doubleValue.rounded())
        let width: CGFloat = 3
        let center = imageCount > 1
            ? (x(forIndex: index) + x(forIndex: index + 1)) / 2
            : bar.midX
        let marker = NSRect(x: center - width / 2,
                            y: bounds.midY - 6,
                            width: width,
                            height: 12)
        NSGraphicsContext.saveGraphicsState()
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.3 * alpha)
        shadow.shadowBlurRadius = 1.5
        shadow.set()
        NSColor.systemRed.withAlphaComponent(alpha).setFill()
        NSBezierPath(roundedRect: marker, xRadius: 1.5, yRadius: 1.5).fill()
        NSGraphicsContext.restoreGraphicsState()
    }
}
