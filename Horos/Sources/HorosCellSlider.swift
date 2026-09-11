import AppKit

/// Cell-drawn slider for Viewer.xib. On macOS 26, stock `NSSlider` decodes
/// into a SwiftUI `_NSCoreHostingView` (`SliderWrapper`) backed by
/// `NSSliderAquaduckVisualProvider`. That AttributeGraph table grows on
/// `initWithCoder` (`loadWindow` → slider decode → `AG::data::table::grow_region`)
/// and does not shrink when the viewer closes.
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
public final class HorosCellSlider: NSSlider {
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

    public override func layout() {
        // Skip NSSlider.layout, which installs SliderWrapper hosts.
    }

    @objc func _layoutComponentSubviewsIfNecessary() {}
    @objc func _updateComponentSubviewRenderingState() {}
    @objc func _clearComponentSubviews() {}

    public override func draw(_ dirtyRect: NSRect) {
        cell?.draw(withFrame: bounds, in: self)
    }

    public override var wantsUpdateLayer: Bool { false }
}
