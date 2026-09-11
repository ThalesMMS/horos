import AppKit

/// How much of a screen Horos may lay its windows out on.
///
/// Tiling has always taken the whole visible frame of every screen, which is
/// wrong on a wide display where the person wants a report application beside
/// the images rather than behind them. The area is a rectangle expressed as
/// fractions of the screen's visible frame, kept per screen, so a laptop and the
/// display it is plugged into can answer differently.
///
/// Nothing here moves a window: `+[AppController usefullRectForScreen:]` is the
/// one place that says where windows may go, and this narrows what it returns.
/// Dragging a window somewhere else by hand still works - this is about where
/// Horos puts them.
@objc(HorosTilingArea)
public final class TilingArea: NSObject {
    /// The preference: screen identifier to {x, y, width, height} in fractions of
    /// that screen's visible frame, origin at its bottom-left corner.
    @objc public static let defaultsKey = "TilingArea"

    /// Smaller than this and a viewer is not worth tiling into, so an area that
    /// would leave less falls back to the whole screen.
    static let smallestUsable = NSSize(width: 320, height: 240)

    @objc(identifierForScreen:)
    public static func identifier(for screen: NSScreen?) -> String {
        guard let screen = screen else { return "" }
        let name = screen.localizedName.trimmingCharacters(in: .whitespaces)
        if !name.isEmpty { return name }
        let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber
        return "Display \(number?.intValue ?? 0)"
    }

    /// The rectangle the fractions describe inside `visibleFrame`, or
    /// `visibleFrame` itself when they describe nothing usable.
    @objc(applyFractions:toVisibleFrame:)
    public static func apply(fractions: [String: NSNumber]?, to visibleFrame: NSRect) -> NSRect {
        guard let fractions = fractions, !fractions.isEmpty else { return visibleFrame }
        func value(_ key: String, _ fallback: CGFloat) -> CGFloat {
            guard let number = fractions[key] else { return fallback }
            let raw = CGFloat(number.doubleValue)
            return raw.isFinite ? min(max(raw, 0), 1) : fallback
        }
        let width = value("width", 1), height = value("height", 1)
        var x = value("x", 0), y = value("y", 0)
        // A rectangle that runs off the right or the top is brought back rather
        // than clipped, so "the right third" stays a third when it is written
        // as x 0.75 width 0.33.
        x = min(x, 1 - width)
        y = min(y, 1 - height)
        let area = NSRect(x: visibleFrame.origin.x + x * visibleFrame.width,
                          y: visibleFrame.origin.y + y * visibleFrame.height,
                          width: width * visibleFrame.width,
                          height: height * visibleFrame.height)
        if area.width < smallestUsable.width || area.height < smallestUsable.height {
            return visibleFrame
        }
        return area
    }

    /// A preference can be written by hand, by `defaults write`, or as a launch
    /// argument, and each of those spells a number differently - "0.5" as a
    /// string is what an old-style plist gives. Take whatever answers as one.
    static func numbers(from entry: [String: Any]) -> [String: NSNumber] {
        var out: [String: NSNumber] = [:]
        for key in ["x", "y", "width", "height"] {
            switch entry[key] {
            case let number as NSNumber: out[key] = number
            case let text as String:
                if let value = Double(text.trimmingCharacters(in: .whitespaces)) {
                    out[key] = NSNumber(value: value)
                }
            default: break
            }
        }
        return out
    }

    @objc(fractionsForScreen:)
    public static func fractions(for screen: NSScreen?) -> [String: NSNumber]? {
        let key = identifier(for: screen)
        guard !key.isEmpty,
              let stored = UserDefaults.standard.dictionary(forKey: defaultsKey),
              let entry = stored[key] as? [String: Any]
        else { return nil }
        let fractions = numbers(from: entry)
        return fractions.isEmpty ? nil : fractions
    }

    /// The area Horos may use on this screen.
    @objc(rectForScreen:visibleFrame:)
    public static func rect(for screen: NSScreen?, visibleFrame: NSRect) -> NSRect {
        apply(fractions: fractions(for: screen), to: visibleFrame)
    }

    @objc(setFractions:forScreen:)
    public static func set(fractions: [String: NSNumber]?, for screen: NSScreen?) {
        let key = identifier(for: screen)
        guard !key.isEmpty else { return }
        var stored = UserDefaults.standard.dictionary(forKey: defaultsKey) ?? [:]
        if let fractions = fractions, !fractions.isEmpty {
            stored[key] = fractions
        } else {
            stored.removeValue(forKey: key)
        }
        UserDefaults.standard.set(stored, forKey: defaultsKey)
    }

    /// The choices the menu offers, in order. `fractions` nil means the whole
    /// screen, which is also what an unset screen does.
    @objc public static let presetNames: [String] = [
        "Whole Screen", "Left Half", "Right Half",
        "Left Two Thirds", "Right Two Thirds", "Top Half", "Bottom Half",
    ]

    @objc(fractionsForPresetNamed:)
    public static func fractions(presetNamed name: String) -> [String: NSNumber]? {
        let third = NSNumber(value: 1.0 / 3.0), twoThirds = NSNumber(value: 2.0 / 3.0)
        let half = NSNumber(value: 0.5), zero = NSNumber(value: 0.0), one = NSNumber(value: 1.0)
        switch name {
        case "Left Half":        return ["x": zero, "y": zero, "width": half, "height": one]
        case "Right Half":       return ["x": half, "y": zero, "width": half, "height": one]
        case "Left Two Thirds":  return ["x": zero, "y": zero, "width": twoThirds, "height": one]
        case "Right Two Thirds": return ["x": third, "y": zero, "width": twoThirds, "height": one]
        case "Top Half":         return ["x": zero, "y": half, "width": one, "height": half]
        case "Bottom Half":      return ["x": zero, "y": zero, "width": one, "height": half]
        default:                 return nil          // Whole Screen, and anything unknown
        }
    }

    /// Which preset a screen is on, for the tick in the menu.
    @objc(presetNameForScreen:)
    public static func presetName(for screen: NSScreen?) -> String {
        let current = fractions(for: screen)
        for name in presetNames where equal(fractions(presetNamed: name), current) { return name }
        return ""                                     // a custom region
    }

    static func equal(_ a: [String: NSNumber]?, _ b: [String: NSNumber]?) -> Bool {
        let left = a ?? [:], right = b ?? [:]
        if left.isEmpty && right.isEmpty { return true }
        for key in ["x", "y", "width", "height"] {
            let l = left[key]?.doubleValue ?? (key == "width" || key == "height" ? 1 : 0)
            let r = right[key]?.doubleValue ?? (key == "width" || key == "height" ? 1 : 0)
            if abs(l - r) > 0.0005 { return false }
        }
        return true
    }
}
