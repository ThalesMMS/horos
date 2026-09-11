import AppKit

/// Resize limits for windows whose nib fixes a minimum designed for a large
/// display. A minimum taller or wider than the display leaves the window
/// unresizable in that direction and makes AppKit displace its origin to keep
/// the requested size, which puts part of the content out of reach.
@objc(HorosWindowSizeLimits)
public final class WindowSizeLimits: NSObject {
    @objc(minimumSize:visibleFrame:)
    public static func minimum(_ designed: NSSize, visibleFrame: NSRect) -> NSSize {
        func limit(_ requested: CGFloat, _ available: CGFloat) -> CGFloat {
            guard requested.isFinite, requested > 0 else { return 0 }
            guard available.isFinite, available > 0 else { return requested }
            return min(requested, available)
        }
        return NSSize(width: limit(designed.width, visibleFrame.width),
                      height: limit(designed.height, visibleFrame.height))
    }

    /// Apply `designed` to `window`, reduced to what the display it is on can
    /// show, and bring the frame back inside that display.
    @objc(applyMinimumSize:toWindow:)
    public static func apply(_ designed: NSSize, to window: NSWindow) {
        guard !window.styleMask.contains(.fullScreen) else { return }
        let visible = (window.screen ?? NSScreen.main)?.visibleFrame ?? .zero
        window.minSize = minimum(designed, visibleFrame: visible)
        DatabaseWindowPlacement.restore(window, savedFrame: window.frame)
    }
}
