import Foundation

/// Window level and width as text, for the fields the user reads and types.
///
/// The values are floats everywhere else: `DCMPix` reads `WindowCenter` and
/// `WindowWidth` with `floatValue`, the presets are stored as `NSNumber`
/// floats, and the annotation already prints four decimals for a narrow window.
/// The two sheets in between did not: Add Current WL/WW showed the current
/// window with `%0.f` and read it back with `intValue`, so an image windowed at
/// WL 0.5 / WW 1 offered "0" and "1", stored 0 and 1, and applied 0 and 1 to the
/// view - the fractional window was gone from the screen as a side effect of
/// looking at it. Set WL/WW manually printed `%.3f`, which keeps the value but
/// writes "400.000" for an ordinary CT window.
///
/// So: as many decimals as the value actually needs, and none when it needs
/// none.
@objc(HorosWindowLevelText)
public final class WindowLevelText: NSObject {
    /// The most decimals a field will show. Matches the annotation's `%0.4f`.
    static let maximumDecimals = 4

    /// `value` as text: an integer when it is one, otherwise the shortest
    /// decimal form that still says what it is.
    @objc(stringForValue:)
    public static func string(for value: Double) -> String {
        guard value.isFinite else { return "0" }
        for decimals in 0...maximumDecimals {
            let text = String(format: "%.\(decimals)f", value)
            if let parsed = Double(text), abs(parsed - value) < tolerance(for: value) {
                return text
            }
        }
        return String(format: "%.\(maximumDecimals)f", value)
    }

    /// Half of the last digit the field would print, so a value is written with
    /// fewer decimals only when nothing is lost at this magnitude.
    static func tolerance(for value: Double) -> Double {
        return max(abs(value), 1) * 1e-7
    }

    /// The number in `text`, or `fallback` when there is no number in it.
    ///
    /// A decimal comma is accepted: the fields are written with a period, and a
    /// user in a comma-decimal locale typing one back would otherwise have had
    /// `-floatValue` read everything before it and drop the rest.
    @objc(valueFromString:fallback:)
    public static func value(from text: String, fallback: Double) -> Double {
        var trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.contains("."), trimmed.contains(",") {
            trimmed = trimmed.replacingOccurrences(of: ",", with: ".")
        }
        guard let value = Double(trimmed), value.isFinite else { return fallback }
        return value
    }

    /// A window width, which may be fractional but may not be zero.
    ///
    /// The callers guarded this with `if (width == 0) width = 1`, which was
    /// reached for every width under 1 once `intValue` had truncated it.
    @objc(widthFromString:fallback:)
    public static func width(from text: String, fallback: Double) -> Double {
        let value = self.value(from: text, fallback: fallback)
        return value == 0 ? 1 : value
    }
}
