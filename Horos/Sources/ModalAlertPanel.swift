import AppKit
import ObjectiveC

/// An alert window for `NSApplication.beginModalSession(for:)`.
///
/// The previous helper returned the window of `NSGetAlertPanel` autoreleased.
/// That function's panel has to be handed back with `NSReleaseAlertPanel`;
/// releasing it as an ordinary object destroys a window the alert still owns,
/// and the alert's own `dealloc` then messages freed memory. The startup wait
/// for an unmounted database volume crashed exactly there, in
/// `-[NSAlert dealloc]`, as soon as the surrounding autorelease pool drained.
@objc(HorosModalAlertPanel)
public final class ModalAlertPanel: NSObject {
    /// The historical answers the modal loops compare against.
    @objc public static let defaultButtonResponse = 1
    @objc public static let alternateButtonResponse = 0

    private static var alertAssociation = 0

    @objc(panelWithTitle:message:defaultButton:alternateButton:icon:endsSheet:)
    public static func panel(title: String, message: String,
                             defaultButton: String, alternateButton: String?,
                             icon: NSImage?, endsSheet: Bool) -> NSWindow {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        if let icon { alert.icon = icon }
        alert.addButton(withTitle: defaultButton)
        if let alternateButton { alert.addButton(withTitle: alternateButton) }
        for (button, response) in zip(alert.buttons, [defaultButtonResponse, alternateButtonResponse]) {
            button.tag = response
            button.target = self
            button.action = endsSheet ? #selector(endSheet(_:)) : #selector(stopModal(_:))
        }
        let window = alert.window
        // The alert owns its window; keep it alive for exactly as long.
        objc_setAssociatedObject(window, &alertAssociation, alert, .OBJC_ASSOCIATION_RETAIN)
        return window
    }

    @objc private static func stopModal(_ sender: NSButton) {
        NSApp.stopModal(withCode: NSApplication.ModalResponse(rawValue: sender.tag))
    }

    @objc private static func endSheet(_ sender: NSButton) {
        guard let window = sender.window else { return }
        window.sheetParent?.endSheet(window, returnCode: NSApplication.ModalResponse(rawValue: sender.tag))
    }
}
