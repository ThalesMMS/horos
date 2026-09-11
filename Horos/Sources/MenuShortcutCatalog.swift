import AppKit
import Foundation

/// Persistent menu shortcuts for plugins and reconstruction viewers.
///
/// The Hot Keys pane still owns single-key viewer tools. This catalogue is
/// the in-app preference for menu items that currently have no equivalent:
/// 2D/3D MPR, curved MPR, MIP, volume rendering, and each plugin title.
/// An assignment that would steal another command is refused.
@objc(HorosMenuShortcutCatalog)
public final class MenuShortcutCatalog: NSObject {
    @objc public static let defaultsKey = "HorosMenuShortcuts"
    @objc public static let didChangeNotification = Notification.Name("HorosMenuShortcutsDidChange")

    @objc public static let orthogonalMPRID = "reconstruction.orthogonalMPR"
    @objc public static let threeDMPRID = "reconstruction.3dMPR"
    @objc public static let curvedMPRID = "reconstruction.curvedMPR"
    @objc public static let mipID = "reconstruction.mip"
    @objc public static let volumeRenderingID = "reconstruction.vr"

    private static let commandFlag = NSEvent.ModifierFlags.command.rawValue
    private static let shiftFlag = NSEvent.ModifierFlags.shift.rawValue
    private static let optionFlag = NSEvent.ModifierFlags.option.rawValue
    private static let controlFlag = NSEvent.ModifierFlags.control.rawValue
    private static let modifierMask: UInt = commandFlag | shiftFlag | optionFlag | controlFlag

    @objc public static func reconstructionCommands() -> [[String: Any]] {
        [
            command(id: orthogonalMPRID, title: "2D Orthogonal MPR", selector: "orthogonalMPRViewer:", tag: 8),
            command(id: threeDMPRID, title: "3D MPR", selector: "mprViewer:", tag: 10),
            command(id: curvedMPRID, title: "3D Curved-MPR", selector: "cprViewer:", tag: 1),
            command(id: mipID, title: "3D MIP", selector: "VRViewer:", tag: 3),
            command(id: volumeRenderingID, title: "3D Volume Rendering", selector: "VRViewer:", tag: 4),
        ]
    }

    @objc(pluginCommandIDWithPlugin:menuTitle:)
    public static func pluginCommandID(plugin: String, menuTitle: String) -> String {
        "plugin.\(plugin).\(menuTitle)"
    }

    @objc public static func pluginCommands(fromDescriptors descriptors: [[String: Any]]) -> [[String: Any]] {
        var result: [[String: Any]] = []
        for descriptor in descriptors {
            guard let name = string(descriptor["name"]), !name.isEmpty else { continue }
            let titles = descriptor["menuTitles"] as? [String] ?? []
            for title in titles where isAssignablePluginTitle(title) {
                result.append([
                    "id": pluginCommandID(plugin: name, menuTitle: title),
                    "title": title,
                    "group": "plugin",
                    "plugin": name,
                ])
            }
        }
        return result
    }

    @objc public static func assignableCommands(pluginDescriptors: [[String: Any]]) -> [[String: Any]] {
        reconstructionCommands() + pluginCommands(fromDescriptors: pluginDescriptors)
    }

    @objc(bindingWithKeyEquivalent:modifierFlags:)
    public static func binding(keyEquivalent: String, modifierFlags: UInt) -> [String: Any] {
        [
            "keyEquivalent": keyEquivalent,
            "modifierFlags": modifierFlags,
        ]
    }

    /// A letter typed without a menu modifier becomes Command+letter.
    @objc(menuBindingWithKeyEquivalent:modifierFlags:)
    public static func menuBinding(keyEquivalent: String, modifierFlags: UInt) -> [String: Any] {
        var flags = modifierFlags & modifierMask
        if !hasMenuModifier(flags) {
            flags |= commandFlag
        }
        return binding(keyEquivalent: keyEquivalent, modifierFlags: flags)
    }

    @objc public static func assignments(from defaults: UserDefaults) -> [String: [String: Any]] {
        guard let stored = defaults.dictionary(forKey: defaultsKey) else { return [:] }
        var result: [String: [String: Any]] = [:]
        for (key, value) in stored {
            if let binding = value as? [String: Any], string(binding["keyEquivalent"])?.isEmpty == false {
                result[key] = [
                    "keyEquivalent": string(binding["keyEquivalent"]) ?? "",
                    "modifierFlags": uint(binding["modifierFlags"]),
                ]
            }
        }
        return result
    }

    @objc public static func save(_ assignments: [String: [String: Any]], to defaults: UserDefaults) {
        var stored: [String: [String: Any]] = [:]
        for (key, binding) in assignments {
            guard let equivalent = string(binding["keyEquivalent"]), !equivalent.isEmpty else { continue }
            stored[key] = [
                "keyEquivalent": equivalent,
                "modifierFlags": uint(binding["modifierFlags"]),
            ]
        }
        defaults.set(stored, forKey: defaultsKey)
        NotificationCenter.default.post(name: didChangeNotification, object: nil)
    }

    @objc public static func proposing(
        assignment: [String: Any]?,
        forCommand commandID: String,
        currentAssignments: [String: [String: Any]],
        occupiedMenuShortcuts: [[String: Any]],
        viewerHotKeys: [String: Any]
    ) -> [String: Any] {
        var next = currentAssignments
        let equivalent = string(assignment?["keyEquivalent"]) ?? ""
        if assignment == nil || equivalent.isEmpty {
            next.removeValue(forKey: commandID)
            return ["accepted": true, "assignments": next]
        }
        let proposed = [
            "keyEquivalent": equivalent,
            "modifierFlags": uint(assignment?["modifierFlags"]),
        ] as [String: Any]
        if let clash = conflict(
            assigning: proposed,
            toCommand: commandID,
            currentAssignments: currentAssignments,
            occupiedMenuShortcuts: occupiedMenuShortcuts,
            viewerHotKeys: viewerHotKeys
        ) {
            return ["accepted": false, "assignments": currentAssignments, "conflict": clash]
        }
        next[commandID] = proposed
        return ["accepted": true, "assignments": next]
    }

    @objc public static func conflict(
        assigning: [String: Any],
        toCommand commandID: String,
        currentAssignments: [String: [String: Any]],
        occupiedMenuShortcuts: [[String: Any]],
        viewerHotKeys: [String: Any]
    ) -> [String: Any]? {
        let signature = shortcutSignature(
            keyEquivalent: string(assigning["keyEquivalent"]) ?? "",
            modifierFlags: uint(assigning["modifierFlags"])
        )
        guard !signature.key.isEmpty else { return nil }

        for (otherID, binding) in currentAssignments where otherID != commandID {
            let other = shortcutSignature(
                keyEquivalent: string(binding["keyEquivalent"]) ?? "",
                modifierFlags: uint(binding["modifierFlags"])
            )
            if other == signature {
                return [
                    "kind": "assignment",
                    "commandID": otherID,
                    "title": title(forCommand: otherID),
                ]
            }
        }

        for item in occupiedMenuShortcuts {
            if let occupiedID = string(item["commandID"]), occupiedID == commandID {
                continue
            }
            let other = shortcutSignature(
                keyEquivalent: string(item["keyEquivalent"]) ?? "",
                modifierFlags: uint(item["modifierFlags"])
            )
            if other == signature {
                return [
                    "kind": "menu",
                    "title": string(item["title"]) ?? "",
                    "commandID": string(item["commandID"]) ?? "",
                ]
            }
        }

        if !hasMenuModifier(signature.flags) {
            for (key, _) in viewerHotKeys {
                let hot = shortcutSignature(keyEquivalent: key, modifierFlags: 0)
                if hot == signature {
                    return ["kind": "hotkey", "key": key, "title": key]
                }
            }
        }
        return nil
    }

    @objc public static func commandID(for item: NSMenuItem) -> String? {
        if item.isSeparatorItem { return nil }
        let action = item.action.map(NSStringFromSelector) ?? ""
        switch action {
        case "orthogonalMPRViewer:":
            return orthogonalMPRID
        case "mprViewer:":
            return threeDMPRID
        case "cprViewer:":
            return curvedMPRID
        case "VRViewer:":
            return item.tag == 3 ? mipID : volumeRenderingID
        case "executeFilter:", "executeFilterDB:", "endBlendingType:":
            guard let plugin = pluginName(from: item.representedObject) else { return nil }
            return pluginCommandID(plugin: plugin, menuTitle: item.title)
        default:
            return nil
        }
    }

    @objc public static func occupiedShortcuts(in menu: NSMenu) -> [[String: Any]] {
        var result: [[String: Any]] = []
        collectOccupiedShortcuts(from: menu, into: &result)
        return result
    }

    @objc public static func apply(_ assignments: [String: [String: Any]], to menu: NSMenu) {
        for item in menu.items {
            if let identifier = commandID(for: item), isManaged(identifier) {
                if let binding = assignments[identifier],
                   let equivalent = string(binding["keyEquivalent"]), !equivalent.isEmpty {
                    item.keyEquivalent = equivalent
                    item.keyEquivalentModifierMask = NSEvent.ModifierFlags(rawValue: uint(binding["modifierFlags"]))
                } else {
                    item.keyEquivalent = ""
                    item.keyEquivalentModifierMask = .command
                }
            }
            if let submenu = item.submenu {
                apply(assignments, to: submenu)
            }
        }
    }

    @objc(applyStoredAssignmentsToMenus:)
    public static func applyStoredAssignments(to menus: [NSMenu]) {
        applyStoredAssignments(from: .standard, to: menus)
    }

    @objc(applyStoredAssignmentsFromDefaults:toMenus:)
    public static func applyStoredAssignments(from defaults: UserDefaults, to menus: [NSMenu]) {
        let stored = assignments(from: defaults)
        for menu in menus {
            apply(stored, to: menu)
        }
    }

    @objc public static func displayString(forBinding binding: [String: Any]?) -> String {
        guard let binding,
              let equivalent = string(binding["keyEquivalent"]), !equivalent.isEmpty else {
            return ""
        }
        return displayString(keyEquivalent: equivalent, modifierFlags: uint(binding["modifierFlags"]))
    }

    @objc public static func displayString(keyEquivalent: String, modifierFlags: UInt) -> String {
        let flags = NSEvent.ModifierFlags(rawValue: modifierFlags)
        var parts = ""
        if flags.contains(.control) { parts += "⌃" }
        if flags.contains(.option) { parts += "⌥" }
        if flags.contains(.shift) { parts += "⇧" }
        if flags.contains(.command) { parts += "⌘" }
        parts += keyEquivalent.uppercased()
        return parts
    }

    @objc public static func pluginDescriptors(fromPluginDictionary dictionary: [AnyHashable: Any]?) -> [[String: Any]] {
        var seen = Set<String>()
        var result: [[String: Any]] = []
        guard let values = dictionary?.values else { return result }
        for value in values {
            guard let bundle = value as? Bundle else { continue }
            let executable = bundle.infoDictionary?["CFBundleExecutable"] as? String
            let name = (executable?.isEmpty == false)
                ? executable!
                : bundle.bundleURL.deletingPathExtension().lastPathComponent
            if name.isEmpty || seen.contains(name) { continue }
            seen.insert(name)
            let titles = (bundle.infoDictionary?["MenuTitles"] as? [String]) ?? []
            result.append(["name": name, "menuTitles": titles])
        }
        return result.sorted { string($0["name"]) ?? "" < string($1["name"]) ?? "" }
    }

    private static func command(id: String, title: String, selector: String, tag: Int) -> [String: Any] {
        [
            "id": id,
            "title": title,
            "group": "reconstruction",
            "selector": selector,
            "tag": tag,
        ]
    }

    private static func isAssignablePluginTitle(_ title: String) -> Bool {
        !title.isEmpty && title != "(-"
    }

    private static func isManaged(_ commandID: String) -> Bool {
        commandID.hasPrefix("reconstruction.") || commandID.hasPrefix("plugin.")
    }

    private static func hasMenuModifier(_ flags: UInt) -> Bool {
        (flags & (commandFlag | optionFlag | controlFlag)) != 0
    }

    private static func pluginName(from represented: Any?) -> String? {
        if let name = represented as? String, !name.isEmpty { return name }
        if let bundle = represented as? Bundle {
            return bundle.infoDictionary?["CFBundleExecutable"] as? String
        }
        if let dictionary = represented as? [String: Any] {
            return string(dictionary["pluginName"]) ?? string(dictionary["name"])
        }
        return nil
    }

    private static func collectOccupiedShortcuts(from menu: NSMenu, into result: inout [[String: Any]]) {
        for item in menu.items {
            if !item.isSeparatorItem, !item.keyEquivalent.isEmpty {
                var entry: [String: Any] = [
                    "title": item.title,
                    "keyEquivalent": item.keyEquivalent,
                    "modifierFlags": item.keyEquivalentModifierMask.rawValue,
                ]
                if let identifier = commandID(for: item) {
                    entry["commandID"] = identifier
                }
                result.append(entry)
            }
            if let submenu = item.submenu {
                collectOccupiedShortcuts(from: submenu, into: &result)
            }
        }
    }

    private static func title(forCommand commandID: String) -> String {
        if let match = reconstructionCommands().first(where: { string($0["id"]) == commandID }) {
            return string(match["title"]) ?? commandID
        }
        if commandID.hasPrefix("plugin.") {
            return String(commandID.dropFirst("plugin.".count))
        }
        return commandID
    }

    private struct ShortcutSignature: Equatable {
        var key: String
        var flags: UInt
    }

    private static func shortcutSignature(keyEquivalent: String, modifierFlags: UInt) -> ShortcutSignature {
        guard let first = keyEquivalent.first else {
            return ShortcutSignature(key: "", flags: 0)
        }
        var flags = modifierFlags & modifierMask
        var key = String(first)
        if first.isLetter, first.isUppercase {
            key = key.lowercased()
            flags |= shiftFlag
        } else {
            key = key.lowercased()
        }
        return ShortcutSignature(key: key, flags: flags)
    }

    private static func string(_ value: Any?) -> String? {
        if let text = value as? String { return text }
        if let number = value as? NSNumber { return number.stringValue }
        return nil
    }

    private static func uint(_ value: Any?) -> UInt {
        if let number = value as? UInt { return number }
        if let number = value as? Int { return UInt(number) }
        if let number = value as? NSNumber { return number.uintValue }
        return 0
    }
}
