import AppKit

/// Menu items for the filters the app provides itself. A plugin bundle declares its items in its
/// Info.plist, and `+[PluginManager setMenus::::]` makes them; T2 Fit Map and ROI Enhancement have no
/// bundle, so they were registered and never reachable from a menu (#653).
@objc(HorosNativeFilterMenus)
public final class NativeFilterMenus: NSObject {
    /// Each native filter: its menu title, the class registered under that title, and whether its
    /// historical bundle was a ROI tool (`roiTool`) rather than an image filter (`imageFilter`).
    private static let filters: [(title: String, className: String, roiTool: Bool)] = [
        ("T2 Fit Map", "T2FitMapFilter", false),
        ("ROI Enhancement", "ROIEnhancementFilter", true),
    ]

    /// Adds an item for each native filter that `plugins` holds under its title, to the image filters or
    /// the ROI tools menu, unless that menu already has an item of the title, at any depth. A compatible
    /// bundle that declares the title has its own item, and its filter is the one registered. The item
    /// sends -executeFilter: to the first responder - the viewer - as a bundle's item does. Returns the
    /// items added.
    @discardableResult
    @objc(addItemsForPlugins:filtersMenu:roisMenu:)
    public static func addItems(for plugins: NSDictionary, filtersMenu: NSMenu, roisMenu: NSMenu) -> [NSMenuItem] {
        var added: [NSMenuItem] = []
        for filter in filters {
            guard let registered = plugins[filter.title] as AnyObject?,
                  NSStringFromClass(type(of: registered)) == filter.className else { continue }
            let menu = filter.roiTool ? roisMenu : filtersMenu
            guard !contains(menu, title: filter.title) else { continue }
            let item = NSMenuItem(title: filter.title, action: NSSelectorFromString("executeFilter:"), keyEquivalent: "")
            item.target = nil
            menu.addItem(item)
            added.append(item)
        }
        return added
    }

    private static func contains(_ menu: NSMenu, title: String) -> Bool {
        menu.items.contains { $0.title == title || ($0.submenu.map { contains($0, title: title) } ?? false) }
    }
}
