import AppKit

/// Resolves application menus independently of translated titles and item order.
@objc(HorosApplicationMenuLookup)
public final class ApplicationMenuLookup: NSObject {
    @objc(submenuInMenu:identifier:)
    public static func submenu(in menu: NSMenu?, identifier: String) -> NSMenu? {
        menu?.items.first { $0.identifier?.rawValue == identifier }?.submenu
    }
}
