import AppKit

/// Native full-screen participation for auxiliary windows that may also float
/// above the others, such as the Query/Retrieve window with Keep on Top set.
@objc(HorosFullScreenWindowSupport)
public final class FullScreenWindowSupport: NSObject {
    /// Collection behavior that lets a window host its own full-screen Space,
    /// preserving the flags that describe Spaces and window cycling.
    @objc(primaryBehaviorFrom:)
    public static func primaryBehavior(from current: NSWindow.CollectionBehavior) -> NSWindow.CollectionBehavior {
        var behavior = current
        behavior.remove(.fullScreenAuxiliary)
        behavior.remove(.fullScreenNone)
        behavior.insert(.fullScreenPrimary)
        return behavior
    }

    /// A window kept above the others cannot host a full-screen Space: AppKit
    /// leaves it over the menu bar and the content becomes unreachable. Keep the
    /// floating level for the windowed state only.
    @objc(levelForKeepOnTop:fullScreen:)
    public static func level(keepOnTop: Bool, fullScreen: Bool) -> NSWindow.Level {
        keepOnTop && !fullScreen ? .floating : .normal
    }

    /// Collection behavior for a window that must never host a full-screen Space
    /// of its own, but may be seen on one another window opened. Horos tiles its
    /// viewers and 3D windows across the screen and has its own full-screen mode,
    /// which moves the content view into a borderless window; a native full-screen
    /// Space is a different thing wearing the same name, and the two cannot both
    /// own the window. Auxiliary says that in public API, and AppKit answers by
    /// leaving the green button on zoom.
    @objc(auxiliaryBehaviorFrom:)
    public static func auxiliaryBehavior(from current: NSWindow.CollectionBehavior) -> NSWindow.CollectionBehavior {
        var behavior = current
        behavior.remove(.fullScreenPrimary)
        behavior.remove(.fullScreenNone)
        behavior.insert(.fullScreenAuxiliary)
        return behavior
    }

    @objc(enablePrimaryFullScreen:)
    public static func enablePrimaryFullScreen(_ window: NSWindow) {
        window.collectionBehavior = primaryBehavior(from: window.collectionBehavior)
    }

    @objc(declineNativeFullScreen:)
    public static func declineNativeFullScreen(_ window: NSWindow?) {
        guard let window = window else { return }
        window.collectionBehavior = auxiliaryBehavior(from: window.collectionBehavior)
    }

    /// Apply the level the current state asks for, without disturbing an active
    /// full-screen transition.
    @objc(applyLevel:keepOnTop:)
    public static func applyLevel(_ window: NSWindow, keepOnTop: Bool) {
        let wanted = level(keepOnTop: keepOnTop, fullScreen: window.styleMask.contains(.fullScreen))
        if window.level != wanted { window.level = wanted }
    }

    /// Enter or leave full screen, declaring the behavior first so a window
    /// loaded from a nib without it still answers the Fullscreen command.
    @objc(toggleFullScreen:)
    public static func toggleFullScreen(_ window: NSWindow) {
        enablePrimaryFullScreen(window)
        window.level = .normal
        window.toggleFullScreen(nil)
    }
}
