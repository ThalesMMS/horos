import AppKit

/// Preserve a custom view's commands when AppKit moves its toolbar item into overflow.
///
/// A single nested popup (Export 3D-SR) keeps the previous copy of that menu.
/// Views that also hold a matrix, checkbox or a second popup — Thick Slab and
/// the mouse-tool palette with Dynamic Angle — append those commands so overflow
/// is not a dead label.
@objc(HorosToolbarMenuBridge)
public final class ToolbarMenuBridge: NSObject {

    @objc(installForItem:)
    public static func install(for item: NSToolbarItem) {
        guard let view = item.view else { return }
        let popups = collect(NSPopUpButton.self, in: view)
        let buttons = collect(NSButton.self, in: view).filter { !($0 is NSPopUpButton) && $0.action != nil }
        let matrices = collect(NSMatrix.self, in: view)

        if popups.count == 1, buttons.isEmpty, matrices.isEmpty,
           let menu = popups[0].menu?.copy() as? NSMenu {
            item.menuFormRepresentation = representation(title: item.label, menu: menu)
            return
        }

        let overflow = NSMenu()
        overflow.autoenablesItems = false

        if popups.count == 1, let copied = popups[0].menu?.copy() as? NSMenu {
            for child in copied.items {
                overflow.addItem(child.copy() as! NSMenuItem)
            }
        } else {
            for popup in popups {
                guard let copied = popup.menu?.copy() as? NSMenu else { continue }
                let heading = NSMenuItem(title: popup.title.isEmpty ? item.label : popup.title,
                                         action: nil,
                                         keyEquivalent: "")
                heading.submenu = copied
                overflow.addItem(heading)
            }
        }

        for button in buttons {
            overflow.addItem(command(title: button.title,
                                     fallback: button.toolTip ?? item.label,
                                     action: button.action,
                                     target: button.target,
                                     tag: button.tag))
        }

        for matrix in matrices {
            for row in 0..<matrix.numberOfRows {
                for column in 0..<matrix.numberOfColumns {
                    guard let cell = matrix.cell(atRow: row, column: column) as? NSActionCell else { continue }
                    overflow.addItem(command(title: cell.title,
                                             fallback: "Tool \(cell.tag)",
                                             action: matrix.action ?? cell.action,
                                             target: matrix.target ?? cell.target,
                                             tag: cell.tag))
                }
            }
        }

        guard overflow.items.contains(where: { !$0.isSeparatorItem && (!$0.isHidden || $0.submenu != nil) }) else {
            return
        }
        item.menuFormRepresentation = representation(title: item.label, menu: overflow)
    }

    @objc(overflowCommandsForItem:)
    public static func overflowCommands(for item: NSToolbarItem) -> [NSMenuItem] {
        flatten(item.menuFormRepresentation?.submenu)
    }

    private static func representation(title: String, menu: NSMenu) -> NSMenuItem {
        let representation = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        representation.submenu = menu
        return representation
    }

    private static func command(title: String,
                                fallback: String,
                                action: Selector?,
                                target: AnyObject?,
                                tag: Int) -> NSMenuItem {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let item = NSMenuItem(title: trimmed.isEmpty ? fallback : trimmed,
                              action: action,
                              keyEquivalent: "")
        item.target = target
        item.tag = tag
        return item
    }

    private static func collect<T: NSView>(_ type: T.Type, in view: NSView) -> [T] {
        var found: [T] = []
        if let match = view as? T {
            found.append(match)
        }
        for child in view.subviews {
            found.append(contentsOf: collect(type, in: child))
        }
        return found
    }

    private static func flatten(_ menu: NSMenu?) -> [NSMenuItem] {
        guard let menu else { return [] }
        var items: [NSMenuItem] = []
        for item in menu.items where !item.isSeparatorItem && !item.isHidden {
            if let submenu = item.submenu {
                items.append(contentsOf: flatten(submenu))
            } else {
                items.append(item)
            }
        }
        return items
    }
}
