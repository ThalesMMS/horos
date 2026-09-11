import AppKit

/// One policy for every window that builds an `NSToolbar`.
///
/// Artwork, overflow menus and plugin overrides already have helpers. This type
/// is the single call each delegate makes after plugins have had their turn, and
/// the place that records what a missing translation is (not a geometry bug),
/// which items must stay out of overflow, and how the detached 2D panel behaves
/// in the host's custom fullscreen.
@objc(HorosToolbarPolicy)
public final class ToolbarPolicy: NSObject {

    @objc public enum LabelKind: Int {
        case translated = 0
        case englishFallback = 1
        case missingTranslation = 2
        case geometricStress = 3
    }

    @objc public enum Presentation: Int {
        case windowed = 0
        case fullscreen = 1
        case overflow = 2
    }

    /// Languages the shipped bundle actually has. Portuguese is not among them;
    /// that absence is a translation gap, not a clipped-label failure.
    @objc(availableLocalizationsInBundle:)
    public static func availableLocalizations(in bundle: Bundle) -> [String] {
        bundle.localizations
            .map { $0.replacingOccurrences(of: "_", with: "-") }
            .filter { $0 != "Base" }
            .sorted()
    }

    @objc(isLanguageAvailable:inLocalizations:)
    public static func isLanguageAvailable(_ language: String, in localizations: [String]) -> Bool {
        let wanted = language.lowercased()
        return localizations.contains { loc in
            let have = loc.lowercased()
            return have == wanted || have.hasPrefix(wanted + "-") || wanted.hasPrefix(have + "-")
        }
    }

    /// Controlled labels for layout stress. They are not catalog copy and must
    /// not be confused with a missing `Localizable.strings` entry.
    @objc(stressLabelForLanguage:)
    public static func stressLabel(for language: String) -> String {
        let code = language.lowercased()
        if code.hasPrefix("pt") {
            return "Projeção de Intensidade Máxima — Espessura do Corte Combinada"
        }
        if code.hasPrefix("de") {
            return "Maximale Intensitätsprojektion — kombinierte Schichtdicke"
        }
        if code.hasPrefix("it") {
            return "Proiezione di Intensità Massima — Spessore di Strato Combinato"
        }
        return "Maximum Intensity Projection — Combined Thick Slab Thickness"
    }

    @objc(classifyLabel:english:localized:requestedLanguage:)
    public static func classify(label: String,
                                english: String,
                                localized: String?,
                                requestedLanguage: String) -> LabelKind {
        if label == stressLabel(for: requestedLanguage) {
            return .geometricStress
        }
        let language = requestedLanguage.lowercased()
        if language.hasPrefix("en") {
            return label == english ? .translated : .englishFallback
        }
        if let localized, localized != english, label == localized {
            return .translated
        }
        if label == english {
            return .missingTranslation
        }
        return .englishFallback
    }

    /// High-priority interactive views stay on the bar (Search, Thick Slab,
    /// mouse-tool palette). Overflow still receives a menu so a narrow window
    /// or a customized order cannot swallow the commands.
    @objc(prepareItem:)
    public static func prepare(_ item: NSToolbarItem?) {
        guard let item else { return }
        ToolbarImage.normalize(for: item)
        ToolbarMenuBridge.install(for: item)
        if containsInteractiveControl(item.view),
           item.visibilityPriority.rawValue < NSToolbarItem.VisibilityPriority.high.rawValue {
            item.visibilityPriority = .high
        }
    }

    @objc(adoptPluginItem:replacing:)
    public static func adopt(plugin: NSToolbarItem?, replacing host: NSToolbarItem?) -> NSToolbarItem? {
        let item = plugin ?? host
        prepare(item)
        return item
    }

    @objc(containsInteractiveControl:)
    public static func containsInteractiveControl(_ view: NSView?) -> Bool {
        guard let view else { return false }
        if view is NSPopUpButton || view is NSSlider || view is NSMatrix || view is NSSearchField {
            return true
        }
        if let button = view as? NSButton, button.action != nil {
            return true
        }
        return view.subviews.contains { containsInteractiveControl($0) }
    }

    /// Prefer high-priority identifiers when the window can no longer show every
    /// item. Widths are in points; the result is identifiers, not views.
    @objc(splitIdentifiers:widths:highPriority:windowWidth:)
    public static func split(identifiers: [String],
                             widths: [NSNumber],
                             highPriority: [String],
                             windowWidth: CGFloat) -> NSDictionary {
        guard identifiers.count == widths.count else {
            return ["visible": identifiers, "overflow": []]
        }
        let preferred = Set(highPriority)
        var remaining = windowWidth
        var visible: [String] = []
        var overflow: [String] = []

        func place(_ identifier: String, at index: Int) {
            let width = CGFloat(truncating: widths[index])
            if remaining >= width {
                visible.append(identifier)
                remaining -= width
            } else {
                overflow.append(identifier)
            }
        }

        for (index, identifier) in identifiers.enumerated() where preferred.contains(identifier) {
            place(identifier, at: index)
        }
        for (index, identifier) in identifiers.enumerated() where !preferred.contains(identifier) {
            place(identifier, at: index)
        }
        return ["visible": visible, "overflow": overflow]
    }

    @objc(actionCatalogForItem:)
    public static func actionCatalog(for item: NSToolbarItem) -> [[String: Any]] {
        var catalog: [[String: Any]] = []
        if item.action != nil {
            catalog.append([
                "title": item.label,
                "tag": item.tag,
                "hasAction": true
            ])
        }
        if let menu = item.menuFormRepresentation?.submenu {
            catalog.append(contentsOf: commands(in: menu))
        }
        return catalog
    }

    @objc(actionsReachable:inPresentation:)
    public static func actionsReachable(_ actions: [[String: Any]],
                                        in presentation: Presentation) -> Bool {
        guard !actions.isEmpty else { return false }
        switch presentation {
        case .windowed:
            return true
        case .fullscreen, .overflow:
            return actions.contains { ($0["hasAction"] as? Bool) == true }
        }
    }

    /// Custom fullscreen covers the screen. Leave the same strip the tiling
    /// already reserves for the detached panel so the toolbar stays clickable
    /// without changing the host's fullscreen policy.
    @objc(fullscreenContentRectOnScreen:reservingPanelHeight:)
    public static func fullscreenContentRect(on screenFrame: NSRect,
                                             reservingPanelHeight height: CGFloat) -> NSRect {
        var rect = screenFrame
        let reserved = max(0, height)
        if rect.size.height > reserved {
            rect.size.height -= reserved
        }
        return rect
    }

    @objc(shouldKeepDetachedToolbarVisibleWhenFullScreen:)
    public static func shouldKeepDetachedToolbarVisible(whenFullScreen fullScreen: Bool) -> Bool {
        fullScreen
    }

    @objc(toolbarPanelLevelWhenFullScreen:)
    public static func toolbarPanelLevel(whenFullScreen fullScreen: Bool) -> Int {
        fullScreen ? Int(CGWindowLevelForKey(.screenSaverWindow)) : Int(CGWindowLevelForKey(.normalWindow))
    }

    private static func commands(in menu: NSMenu) -> [[String: Any]] {
        var result: [[String: Any]] = []
        for item in menu.items where !item.isSeparatorItem && !item.isHidden {
            if let submenu = item.submenu {
                result.append(contentsOf: commands(in: submenu))
            } else if item.action != nil {
                result.append([
                    "title": item.title,
                    "tag": item.tag,
                    "hasAction": true
                ])
            }
        }
        return result
    }
}
