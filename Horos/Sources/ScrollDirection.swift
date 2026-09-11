import AppKit

/// One direction policy for every gesture that walks through a series.
///
/// Three independent things decide which way a gesture moves: the user's
/// `Scroll Wheel Reversed` preference, whether the series order is flipped, and
/// — outside the app — whether macOS delivers the scroll deltas inverted
/// ("natural" scrolling). Before this the wheel applied the preference and the
/// flipped order while the click-drag applied neither, so the same series moved
/// one way under the wheel and the other way under a drag as soon as either was
/// in play.
///
/// The convention is expressed once, as the sign a gesture's own positive axis
/// contributes to the image index:
///
/// - the wheel's positive axis is a positive `deltaY`, which is the wheel or the
///   fingers moving *up* while macOS natural scrolling is off;
/// - the drag's positive axis is the pointer moving *down* and *right*, which is
///   how a stack scroll has always worked here.
///
/// Those two axes point at each other, so `drag` is the mirror of `wheel`. That
/// is what makes the shipped configuration — `Scroll Wheel Reversed` on, which
/// is the default — agree: wheel down and drag down both advance. Flipping the
/// series order inverts both together, and the preference inverts both together.
@objc(HorosScrollDirection)
public final class ScrollDirection: NSObject {
    @objc public static let reversedPreferenceKey = "Scroll Wheel Reversed"

    /// Multiplier for a scroll event's vertical delta.
    @objc(wheelSignReversed:flippedData:)
    public static func wheelSign(reversed: Bool, flippedData: Bool) -> Double {
        (reversed ? -1.0 : 1.0) * (flippedData ? -1.0 : 1.0)
    }

    /// Multiplier for a click-drag's movement along its own axis.
    @objc(dragSignReversed:flippedData:)
    public static func dragSign(reversed: Bool, flippedData: Bool) -> Double {
        -wheelSign(reversed: reversed, flippedData: flippedData)
    }

    /// The preference as the defaults currently hold it.
    @objc(reversedPreferenceInDefaults:)
    public static func reversedPreference(in defaults: UserDefaults) -> Bool {
        defaults.bool(forKey: reversedPreferenceKey)
    }

    @objc(wheelSignForFlippedData:)
    public static func wheelSign(flippedData: Bool) -> Double {
        wheelSign(reversed: reversedPreference(in: .standard), flippedData: flippedData)
    }

    @objc(dragSignForFlippedData:)
    public static func dragSign(flippedData: Bool) -> Double {
        dragSign(reversed: reversedPreference(in: .standard), flippedData: flippedData)
    }

    /// Undoes the inversion macOS applies to a scroll event when "natural"
    /// scrolling is on, given `NSEvent.isDirectionInvertedFromDevice`.
    ///
    /// A click-drag carries no such inversion. Leaving it in place therefore made
    /// a system-wide setting decide whether the wheel and the drag agreed, and on
    /// the shipped defaults — natural scrolling on, `Scroll Wheel Reversed` on —
    /// they did not. Removing it here makes a physical gesture mean the same
    /// thing on every Mac and leaves the preference as the one control that
    /// changes the direction.
    @objc(deviceOrientationSignInverted:)
    public static func deviceOrientationSign(inverted: Bool) -> Double {
        inverted ? -1.0 : 1.0
    }
}
