import AppKit

/// Temporarily holds a rendering surface steady against AppKit layout.
/// A zero pixel size preserves the existing frame; positive sizes select a square target.
@objc(HorosVRExportLayout)
public final class VRExportLayout: NSObject {
    private weak var view: NSView?
    private let savedFrame: NSRect
    private let savedMask: NSView.AutoresizingMask
    private let savedTranslation: Bool
    private var savedConstraints: [NSLayoutConstraint] = []

    @objc(initWithView:pixelSize:)
    public init(view: NSView, pixelSize: CGFloat) {
        self.view = view
        savedFrame = view.frame
        savedMask = view.autoresizingMask
        savedTranslation = view.translatesAutoresizingMaskIntoConstraints
        super.init()

        var ancestor: NSView? = view
        while let owner = ancestor {
            savedConstraints += owner.constraints.filter {
                $0.isActive && (($0.firstItem as? NSView) === view || ($0.secondItem as? NSView) === view)
            }
            ancestor = owner.superview
        }
        NSLayoutConstraint.deactivate(savedConstraints)
        view.translatesAutoresizingMaskIntoConstraints = true
        view.autoresizingMask = []
        guard pixelSize > 0 else { return }
        let size = view.convertFromBacking(NSSize(width: pixelSize, height: pixelSize))
        let container = view.superview?.bounds ?? savedFrame
        view.frame = NSRect(x: container.midX - size.width / 2,
                            y: container.midY - size.height / 2,
                            width: size.width, height: size.height)
    }

    @objc public func restore() {
        guard let view else { return }
        view.frame = savedFrame
        view.autoresizingMask = savedMask
        view.translatesAutoresizingMaskIntoConstraints = savedTranslation
        NSLayoutConstraint.activate(savedConstraints)
        savedConstraints.removeAll()
        self.view = nil
        view.superview?.layoutSubtreeIfNeeded()
    }
}
