import AppKit

/// The borderless progress panel participates in a modal session with an Abort button.
@objc(HorosProgressPanel)
public final class ProgressPanel: NSPanel {
    public override var canBecomeKey: Bool { true }
    public override var canBecomeMain: Bool { false }
}
