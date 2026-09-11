import AppKit

@objc(HorosVRInteractionGeometry)
public final class VRInteractionGeometry: NSObject {
    /// VTK consumes view-local backing pixels; NSEvent locations are window points.
    @objc(backingPoint:inView:)
    public static func backingPoint(_ windowPoint: NSPoint, in view: NSView) -> NSPoint {
        view.convertToBacking(view.convert(windowPoint, from: nil))
    }
}
