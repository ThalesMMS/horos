import AppKit

/// Geometry shared by initial restoration and the explicit Show Database action.
@objc(HorosDatabaseWindowPlacement)
public final class DatabaseWindowPlacement: NSObject {
    @objc(recoveredFrame:visibleFrames:minimumSize:)
    public static func recoveredFrame(_ saved: NSRect, visibleFrames: [NSValue], minimumSize: NSSize) -> NSRect {
        func valid(_ rect: NSRect) -> Bool {
            [rect.origin.x, rect.origin.y, rect.width, rect.height].allSatisfy { $0.isFinite }
                && rect.width > 0 && rect.height > 0
        }
        let screens = visibleFrames.map { $0.rectValue }.filter(valid)
        guard let fallback = screens.first else { return saved }
        guard valid(saved) else { return fallback }
        // Keep a window on its existing display whenever it still overlaps one.
        // Otherwise use the nearest display, including displays with negative origins.
        let target = screens.max { lhs, rhs in
            func area(_ rect: NSRect) -> CGFloat {
                let intersection = saved.intersection(rect)
                return intersection.isNull ? 0 : intersection.width * intersection.height
            }
            let left = area(lhs), right = area(rhs)
            if left != right { return left < right }
            func distance(_ rect: NSRect) -> CGFloat {
                hypot(saved.midX - rect.midX, saved.midY - rect.midY)
            }
            return distance(lhs) > distance(rhs)
        } ?? fallback
        func dimension(_ requested: CGFloat, _ minimum: CGFloat, _ available: CGFloat) -> CGFloat {
            min(max(requested, minimum.isFinite ? max(0, minimum) : 0), available)
        }
        let width = dimension(saved.width, minimumSize.width, target.width)
        let height = dimension(saved.height, minimumSize.height, target.height)
        return NSRect(x: min(max(saved.minX, target.minX), target.maxX - width),
                      y: min(max(saved.minY, target.minY), target.maxY - height),
                      width: width, height: height)
    }

    @objc(restoreWindow:savedFrame:)
    public static func restore(_ window: NSWindow, savedFrame: NSRect) {
        guard !window.styleMask.contains(.fullScreen) else { return }
        let recovered = recoveredFrame(savedFrame,
                                       visibleFrames: NSScreen.screens.map { NSValue(rect: $0.visibleFrame) },
                                       minimumSize: window.minSize)
        if recovered != window.frame { window.setFrame(recovered, display: true) }
    }
}
