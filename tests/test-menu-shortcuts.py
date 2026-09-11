#!/usr/bin/env python3
"""Assignable plugin and reconstruction shortcuts persist and refuse conflicts.

Issue #154: configure shortcuts for plugins, MPR and VR inside Horos, persist
them, and detect a clash with a command that already owns the same key.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/MenuShortcutCatalog.swift'
if not source.is_file():
    raise SystemExit('FAIL MenuShortcutCatalog.swift is the new Swift component')

code = r'''
import AppKit
import Foundation

var failures = 0
func check(_ condition: Bool, _ what: String) {
    if !condition { print("FAIL \(what)"); failures += 1 }
}

let catalog = MenuShortcutCatalog.self
let command = UInt(NSEvent.ModifierFlags.command.rawValue)
let suite = "horos-menu-shortcut-test-\(ProcessInfo.processInfo.processIdentifier)"
let defaults = UserDefaults(suiteName: suite)!
defaults.removePersistentDomain(forName: suite)

let reconstructions = catalog.reconstructionCommands()
let reconstructionIDs = reconstructions.compactMap { $0["id"] as? String }
check(reconstructionIDs.contains(catalog.orthogonalMPRID), "2D Orthogonal MPR is assignable")
check(reconstructionIDs.contains(catalog.threeDMPRID), "3D MPR is assignable")
check(reconstructionIDs.contains(catalog.curvedMPRID), "curved MPR is assignable")
check(reconstructionIDs.contains(catalog.mipID), "MIP is assignable")
check(reconstructionIDs.contains(catalog.volumeRenderingID), "volume rendering is assignable")
check(reconstructions.allSatisfy { ($0["group"] as? String) == "reconstruction" },
      "reconstructions stay in their own group")

let plugins = catalog.pluginCommands(fromDescriptors: [
    ["name": "BoneRemoval", "menuTitles": ["Bone Removal", "(-", "Settings"]],
    ["name": "T2Fit", "menuTitles": ["T2 Fit Map"]],
])
let pluginIDs = plugins.compactMap { $0["id"] as? String }
check(pluginIDs.contains(catalog.pluginCommandID(plugin: "BoneRemoval", menuTitle: "Bone Removal")),
      "a plugin menu title is addressable")
check(pluginIDs.contains(catalog.pluginCommandID(plugin: "BoneRemoval", menuTitle: "Settings")),
      "a second title on the same plugin is a distinct command")
check(!pluginIDs.contains(where: { $0.contains("(-") }), "separators are not assignable")
check(plugins.allSatisfy { ($0["group"] as? String) == "plugin" }, "plugins stay in their own group")

let assignable = catalog.assignableCommands(pluginDescriptors: [
    ["name": "BoneRemoval", "menuTitles": ["Bone Removal"]],
])
check(assignable.count == reconstructions.count + 1, "the list is reconstructions plus loaded plugins")

let cmdM = catalog.menuBinding(keyEquivalent: "m", modifierFlags: 0)
check((cmdM["keyEquivalent"] as? String) == "m", "a typed letter is kept")
check((cmdM["modifierFlags"] as? UInt) == command, "a typed letter becomes a menu Command shortcut")

let alreadyCmdM = catalog.menuBinding(keyEquivalent: "m", modifierFlags: command)
check((alreadyCmdM["modifierFlags"] as? UInt) == command, "Command+M is stored as typed")

let empty = catalog.assignments(from: defaults)
check(empty.isEmpty, "nothing is stored until the user assigns a shortcut")

var stored: [String: [String: Any]] = [:]
let first = catalog.proposing(
    assignment: cmdM,
    forCommand: catalog.volumeRenderingID,
    currentAssignments: stored,
    occupiedMenuShortcuts: [],
    viewerHotKeys: ["m": 14]
)
check((first["accepted"] as? Bool) == true, "Command+M does not clash with the viewer Move hot key")
stored = first["assignments"] as? [String: [String: Any]] ?? [:]
catalog.save(stored, to: defaults)
let loaded = catalog.assignments(from: defaults)
check(loaded[catalog.volumeRenderingID]?["keyEquivalent"] as? String == "m",
      "the VR shortcut is persisted")
check(loaded[catalog.volumeRenderingID]?["modifierFlags"] as? UInt == command,
      "the persisted VR shortcut keeps Command")

let pluginID = catalog.pluginCommandID(plugin: "BoneRemoval", menuTitle: "Bone Removal")
let clashAssignment = catalog.proposing(
    assignment: cmdM,
    forCommand: pluginID,
    currentAssignments: stored,
    occupiedMenuShortcuts: [],
    viewerHotKeys: ["m": 14]
)
check((clashAssignment["accepted"] as? Bool) == false, "the same shortcut cannot bind two commands")
check((clashAssignment["conflict"] as? [String: Any])?["kind"] as? String == "assignment",
      "the clash names the other assignment")
check((clashAssignment["assignments"] as? [String: [String: Any]])?.keys.contains(pluginID) != true,
      "a refused assignment is not stored")

let quit: [String: Any] = [
    "title": "Quit Horos",
    "keyEquivalent": "q",
    "modifierFlags": command,
]
let clashMenu = catalog.proposing(
    assignment: catalog.menuBinding(keyEquivalent: "q", modifierFlags: command),
    forCommand: catalog.threeDMPRID,
    currentAssignments: stored,
    occupiedMenuShortcuts: [quit],
    viewerHotKeys: [:]
)
check((clashMenu["accepted"] as? Bool) == false, "a built-in menu command keeps its shortcut")
check((clashMenu["conflict"] as? [String: Any])?["kind"] as? String == "menu",
      "the clash names the existing menu command")
check((clashMenu["conflict"] as? [String: Any])?["title"] as? String == "Quit Horos",
      "the user sees which command already owns the key")

let bareM = catalog.binding(keyEquivalent: "m", modifierFlags: 0)
let clashHotkey = catalog.proposing(
    assignment: bareM,
    forCommand: catalog.orthogonalMPRID,
    currentAssignments: stored,
    occupiedMenuShortcuts: [],
    viewerHotKeys: ["m": 14]
)
check((clashHotkey["accepted"] as? Bool) == false, "a bare key still owned by the Hot Keys pane is refused")
check((clashHotkey["conflict"] as? [String: Any])?["kind"] as? String == "hotkey",
      "the clash names the viewer hot key")

let replace = catalog.proposing(
    assignment: catalog.menuBinding(keyEquivalent: "p", modifierFlags: command),
    forCommand: catalog.volumeRenderingID,
    currentAssignments: stored,
    occupiedMenuShortcuts: [],
    viewerHotKeys: ["m": 14]
)
check((replace["accepted"] as? Bool) == true, "the same command may change its shortcut")
stored = replace["assignments"] as? [String: [String: Any]] ?? [:]
check(stored[catalog.volumeRenderingID]?["keyEquivalent"] as? String == "p",
      "the new VR shortcut replaces the old one")

let cleared = catalog.proposing(
    assignment: nil,
    forCommand: catalog.volumeRenderingID,
    currentAssignments: stored,
    occupiedMenuShortcuts: [quit],
    viewerHotKeys: ["m": 14]
)
check((cleared["accepted"] as? Bool) == true, "clearing a shortcut is always allowed")
stored = cleared["assignments"] as? [String: [String: Any]] ?? [:]
check(stored[catalog.volumeRenderingID] == nil, "a cleared shortcut is forgotten")

let main = NSMenu(title: "Main")
let viewer3D = NSMenuItem(title: "3D Viewer", action: nil, keyEquivalent: "")
let reconstructionsMenu = NSMenu(title: "3D Viewer")
let mpr = NSMenuItem(title: "3D MPR", action: Selector(("mprViewer:")), keyEquivalent: "")
mpr.tag = 10
let cpr = NSMenuItem(title: "3D Curved-MPR", action: Selector(("cprViewer:")), keyEquivalent: "")
cpr.tag = 1
let ortho = NSMenuItem(title: "2D Orthogonal MPR", action: Selector(("orthogonalMPRViewer:")), keyEquivalent: "")
ortho.tag = 8
let mip = NSMenuItem(title: "3D MIP", action: Selector(("VRViewer:")), keyEquivalent: "")
mip.tag = 3
let vr = NSMenuItem(title: "3D Volume Rendering", action: Selector(("VRViewer:")), keyEquivalent: "")
vr.tag = 4
for item in [mpr, cpr, ortho, mip, vr] { reconstructionsMenu.addItem(item) }
viewer3D.submenu = reconstructionsMenu
main.addItem(viewer3D)

let pluginsMenu = NSMenuItem(title: "Plugins", action: nil, keyEquivalent: "")
let filters = NSMenu(title: "Image Filters")
let bone = NSMenuItem(title: "Bone Removal", action: Selector(("executeFilter:")), keyEquivalent: "")
bone.representedObject = "BoneRemoval"
filters.addItem(bone)
pluginsMenu.submenu = filters
main.addItem(pluginsMenu)

let quitItem = NSMenuItem(title: "Quit Horos", action: Selector(("terminate:")), keyEquivalent: "q")
quitItem.keyEquivalentModifierMask = .command
main.addItem(quitItem)

check(catalog.commandID(for: mpr) == catalog.threeDMPRID, "3D MPR is identified by its action")
check(catalog.commandID(for: cpr) == catalog.curvedMPRID, "curved MPR is identified by its action")
check(catalog.commandID(for: ortho) == catalog.orthogonalMPRID, "2D MPR is identified by its action")
check(catalog.commandID(for: mip) == catalog.mipID, "MIP is the VR action with tag 3")
check(catalog.commandID(for: vr) == catalog.volumeRenderingID, "VR is the VR action with tag 4")
check(catalog.commandID(for: bone) == pluginID, "a plugin item is identified by bundle and title")

let occupied = catalog.occupiedShortcuts(in: main)
check(occupied.contains { ($0["title"] as? String) == "Quit Horos" },
      "occupied shortcuts include built-in menu commands")

let toApply: [String: [String: Any]] = [
    catalog.threeDMPRID: catalog.menuBinding(keyEquivalent: "3", modifierFlags: command),
    pluginID: catalog.menuBinding(keyEquivalent: "b", modifierFlags: command),
]
catalog.apply(toApply, to: main)
check(mpr.keyEquivalent == "3", "the 3D MPR menu item receives its shortcut")
check(mpr.keyEquivalentModifierMask == .command, "3D MPR keeps Command")
check(bone.keyEquivalent == "b", "the plugin menu item receives its shortcut")
check(vr.keyEquivalent == "", "an unassigned reconstruction is left without a shortcut")
check(quitItem.keyEquivalent == "q", "applying does not steal a built-in shortcut")

catalog.apply([:], to: main)
check(mpr.keyEquivalent == "", "removing the assignment clears the reconstruction shortcut")
check(bone.keyEquivalent == "", "removing the assignment clears the plugin shortcut")
check(quitItem.keyEquivalent == "q", "clearing assignments leaves built-in shortcuts alone")

if failures == 0 {
    print("ok: plugin and reconstruction shortcuts persist and refuse conflicts")
} else {
    print("FAIL \(failures) checks")
    exit(1)
}
'''

with tempfile.TemporaryDirectory(prefix='horos-menu-shortcut-') as temp:
    folder = Path(temp)
    (folder / 'main.swift').write_text(code)
    binary = folder / 'probe'
    build = subprocess.run(
        ['xcrun', 'swiftc',
         str(source),
         str(folder / 'main.swift'),
         '-framework', 'AppKit',
         '-o', str(binary)],
        capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
