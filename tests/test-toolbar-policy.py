#!/usr/bin/env python3
"""Toolbar policy: overflow of Thick Slab/Dynamic Angle, locales, narrow window, fullscreen."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
code = r'''
import AppKit

final class Receiver: NSObject {
    var received: [Int] = []
    @objc func setROITool(_ sender: NSMenuItem) { received.append(sender.tag) }
    @objc func popFusion(_ sender: NSMenuItem) { received.append(sender.tag) }
    @objc func activateFusion(_ sender: NSMenuItem) { received.append(100) }
    @objc func setDefaultTool(_ sender: NSMenuItem) { received.append(sender.tag) }
    @objc func exportFormat(_ sender: NSMenuItem) { received.append(sender.tag) }
}

@main struct Test {
    static func main() {
        _ = NSApplication.shared
        let receiver = Receiver()

        singlePopupStillCopiesMenu(receiver)
        thickSlabKeepsModeAndProjection(receiver)
        toolsPaletteKeepsDynamicAngle(receiver)
        localesDistinguishTranslationFromGeometry()
        narrowWindowKeepsInteractiveItems()
        pluginOverrideThenPrepare()
        fullscreenLeavesRoomForPanel()
        print("PASS: toolbar policy covers overflow commands, locales, narrow windows, plugins and fullscreen")
    }

    static func singlePopupStillCopiesMenu(_ receiver: Receiver) {
        receiver.received.removeAll()
        let toolbar = NSToolbarItem(itemIdentifier: .init("export"))
        toolbar.label = "Export 3D-SR"
        let container = NSView()
        let popup = NSPopUpButton(frame: .zero, pullsDown: true)
        container.addSubview(popup)
        let source = NSMenu()
        source.autoenablesItems = false
        let placeholder = NSMenuItem()
        placeholder.isHidden = true
        source.addItem(placeholder)
        for index in 1...5 {
            let command = NSMenuItem(title: "Format \(index)",
                                     action: #selector(Receiver.exportFormat(_:)),
                                     keyEquivalent: "")
            command.target = receiver
            command.tag = index
            source.addItem(command)
        }
        popup.menu = source
        toolbar.view = container
        ToolbarPolicy.prepare(toolbar)
        let overflow = toolbar.menuFormRepresentation!.submenu!
        precondition(overflow.items.count == 6 && overflow.items[0].isHidden)
        overflow.performActionForItem(at: 3)
        precondition(receiver.received == [3])
    }

    static func thickSlabKeepsModeAndProjection(_ receiver: Receiver) {
        receiver.received.removeAll()
        let fusion = NSView(frame: NSRect(x: 0, y: 0, width: 230, height: 41))
        let mode = NSButton(checkboxWithTitle: "Mode:", target: receiver, action: #selector(Receiver.activateFusion(_:)))
        let popup = NSPopUpButton(frame: .zero, pullsDown: false)
        let menu = NSMenu()
        menu.autoenablesItems = false
        for (title, tag) in [("Mean", 1), ("MIP - Max Intensity Projection", 2), ("MinIP - Min Intensity Projection", 3)] {
            let command = NSMenuItem(title: title, action: #selector(Receiver.popFusion(_:)), keyEquivalent: "")
            command.target = receiver
            command.tag = tag
            menu.addItem(command)
        }
        popup.menu = menu
        fusion.addSubview(mode)
        fusion.addSubview(popup)
        fusion.addSubview(NSSlider(value: 20, minValue: 2, maxValue: 128, target: nil, action: nil))

        let item = NSToolbarItem(itemIdentifier: .init("Fusion"))
        item.label = "Thick Slab"
        item.view = fusion
        ToolbarPolicy.prepare(item)
        precondition(item.visibilityPriority == .high)
        let commands = ToolbarMenuBridge.overflowCommands(for: item)
        precondition(commands.contains { $0.title == "Mode:" })
        precondition(commands.contains { $0.title.contains("MIP") && $0.tag == 2 })
        if let mip = commands.first(where: { $0.tag == 2 }) {
            NSApp.sendAction(mip.action!, to: mip.target, from: mip)
        }
        if let modeCommand = commands.first(where: { $0.title == "Mode:" }) {
            NSApp.sendAction(modeCommand.action!, to: modeCommand.target, from: modeCommand)
        }
        precondition(receiver.received == [2, 100])
        let catalog = ToolbarPolicy.actionCatalog(for: item)
        precondition(ToolbarPolicy.actionsReachable(catalog, in: .windowed))
        precondition(ToolbarPolicy.actionsReachable(catalog, in: .overflow))
        precondition(ToolbarPolicy.actionsReachable(catalog, in: .fullscreen))
    }

    static func toolsPaletteKeepsDynamicAngle(_ receiver: Receiver) {
        receiver.received.removeAll()
        let tools = NSView(frame: NSRect(x: 0, y: 0, width: 200, height: 50))
        let popup = NSPopUpButton(frame: .zero, pullsDown: true)
        let roi = NSMenu()
        roi.autoenablesItems = false
        for (title, tag) in [("Length", 5), ("Axis", 26), ("Dynamic Angle", 27)] {
            let command = NSMenuItem(title: title, action: #selector(Receiver.setROITool(_:)), keyEquivalent: "")
            command.target = receiver
            command.tag = tag
            roi.addItem(command)
        }
        popup.menu = roi
        let matrix = NSMatrix(frame: NSRect(x: 0, y: 0, width: 64, height: 32))
        matrix.renewRows(1, columns: 2)
        (matrix.cell(atRow: 0, column: 0) as? NSCell)?.title = "Levels"
        (matrix.cell(atRow: 0, column: 0) as? NSCell)?.tag = 0
        (matrix.cell(atRow: 0, column: 1) as? NSCell)?.title = "Move"
        (matrix.cell(atRow: 0, column: 1) as? NSCell)?.tag = 1
        matrix.action = #selector(Receiver.setDefaultTool(_:))
        matrix.target = receiver
        tools.addSubview(popup)
        tools.addSubview(matrix)

        let item = NSToolbarItem(itemIdentifier: .init("Tools"))
        item.label = "Mouse button function"
        item.view = tools
        ToolbarPolicy.prepare(item)
        precondition(item.visibilityPriority == .high)
        let commands = ToolbarMenuBridge.overflowCommands(for: item)
        precondition(commands.contains { $0.title == "Dynamic Angle" && $0.tag == 27 })
        precondition(commands.contains { $0.title == "Levels" })
        if let angle = commands.first(where: { $0.tag == 27 }) {
            NSApp.sendAction(angle.action!, to: angle.target, from: angle)
        }
        precondition(receiver.received == [27])
    }

    static func localesDistinguishTranslationFromGeometry() {
        let bundle = Bundle(path: CommandLine.arguments[1])!
        let localizations = ToolbarPolicy.availableLocalizations(in: bundle)
        precondition(ToolbarPolicy.isLanguageAvailable("en", in: localizations))
        precondition(ToolbarPolicy.isLanguageAvailable("ja-JP", in: localizations))
        precondition(!ToolbarPolicy.isLanguageAvailable("pt", in: localizations))
        precondition(!ToolbarPolicy.isLanguageAvailable("pt-BR", in: localizations))

        precondition(ToolbarPolicy.classify(label: "Thick Slab",
                                            english: "Thick Slab",
                                            localized: "Thick Slab",
                                            requestedLanguage: "en") == .translated)
        precondition(ToolbarPolicy.classify(label: "Thick Slab",
                                            english: "Thick Slab",
                                            localized: nil,
                                            requestedLanguage: "pt") == .missingTranslation)
        let stress = ToolbarPolicy.stressLabel(for: "de")
        precondition(stress.count > "Thick Slab".count)
        precondition(ToolbarPolicy.classify(label: stress,
                                            english: "Thick Slab",
                                            localized: nil,
                                            requestedLanguage: "de") == .geometricStress)

        let englishWidth = ("Thick Slab" as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: NSFont.systemFontSize)]).width
        let stressWidth = (stress as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: NSFont.systemFontSize)]).width
        precondition(stressWidth > englishWidth)
    }

    static func narrowWindowKeepsInteractiveItems() {
        let split = ToolbarPolicy.split(identifiers: ["Search", "Tools", "Fusion", "Interval", "Modality"],
                                        widths: [120, 180, 230, 100, 100],
                                        highPriority: ["Search", "Tools", "Fusion"],
                                        windowWidth: 600) as! [String: [String]]
        precondition(split["visible"]!.contains("Search"))
        precondition(split["visible"]!.contains("Tools"))
        precondition(split["visible"]!.contains("Fusion"))
        precondition(split["overflow"]!.contains("Interval"))
        precondition(split["overflow"]!.contains("Modality"))
    }

    static func pluginOverrideThenPrepare() {
        let host = NSToolbarItem(itemIdentifier: .init("host"))
        host.image = NSImage(size: NSSize(width: 569, height: 569))
        let plugin = NSToolbarItem(itemIdentifier: .init("plugin"))
        plugin.image = NSImage(size: NSSize(width: 200, height: 100))
        let adopted = ToolbarPolicy.adopt(plugin: plugin, replacing: host)!
        precondition(adopted === plugin)
        precondition(max(adopted.image!.size.width, adopted.image!.size.height) <= 32)
        precondition(abs(adopted.image!.size.width / adopted.image!.size.height - 2) < 0.0001)
    }

    static func fullscreenLeavesRoomForPanel() {
        let screen = NSRect(x: 0, y: 0, width: 1680, height: 1050)
        let content = ToolbarPolicy.fullscreenContentRect(on: screen, reservingPanelHeight: 86)
        precondition(content.size.height == 964)
        precondition(content.origin == .zero)
        precondition(ToolbarPolicy.shouldKeepDetachedToolbarVisible(whenFullScreen: true))
        precondition(ToolbarPolicy.toolbarPanelLevel(whenFullScreen: true) >
                     ToolbarPolicy.toolbarPanelLevel(whenFullScreen: false))
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-toolbar-policy-') as folder:
    bundle = Path(folder) / 'Loc.bundle'
    resources = bundle / 'Contents' / 'Resources'
    resources.mkdir(parents=True)
    (bundle / 'Contents' / 'Info.plist').write_text(
        '<?xml version="1.0"?><plist version="1.0"><dict>'
        '<key>CFBundleIdentifier</key><string>br.horos.toolbar-policy</string>'
        '<key>CFBundlePackageType</key><string>BNDL</string>'
        '</dict></plist>\n')
    for language in ('en', 'ja-JP', 'it-IT', 'es'):
        (resources / f'{language}.lproj').mkdir()
    test = Path(folder) / 'test.swift'
    test.write_text(code)
    binary = Path(folder) / 'test'
    sources = [
        root / 'Horos/Sources/ToolbarImage.swift',
        root / 'Horos/Sources/ToolbarMenuBridge.swift',
        root / 'Horos/Sources/ToolbarPolicy.swift',
        test,
    ]
    subprocess.run(
        ['xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library',
         *[str(path) for path in sources], '-framework', 'AppKit', '-o', str(binary)],
        check=True)
    subprocess.run([str(binary), str(bundle)], check=True)
