import AppKit
import PreferencePanes

/// Preference pane that assigns persistent shortcuts to plugins and reconstructions.
@objc(HorosMenuShortcutPref)
public final class MenuShortcutPref: NSPreferencePane, NSTableViewDataSource, NSTableViewDelegate {
    private var commands: [[String: Any]] = []
    private var assignments: [String: [String: Any]] = [:]
    private var captureTable: ShortcutCaptureTable!
    private var status: NSTextField!

    public override init(bundle: Bundle) {
        super.init(bundle: bundle)
        let view = buildView()
        perform(NSSelectorFromString("setMainView:"), with: view)
        reloadCommands()
    }

    public override func mainViewDidLoad() {
        reloadCommands()
        captureTable.reloadData()
    }

    public override func willUnselect() {
        persistAndApply()
        mainView.window?.makeFirstResponder(nil)
    }

    public func numberOfRows(in tableView: NSTableView) -> Int {
        commands.count
    }

    public func tableView(_ tableView: NSTableView, objectValueFor tableColumn: NSTableColumn?, row: Int) -> Any? {
        guard row >= 0, row < commands.count else { return nil }
        let command = commands[row]
        switch tableColumn?.identifier.rawValue {
        case "group":
            return groupLabel(command["group"] as? String)
        case "command":
            return commandTitle(command)
        case "shortcut":
            return MenuShortcutCatalog.displayString(forBinding: assignments[commandID(command)])
        default:
            return nil
        }
    }

    @objc private func captureKey(_ event: NSEvent) {
        guard captureTable.selectedRow >= 0, captureTable.selectedRow < commands.count else { return }
        let identifier = commandID(commands[captureTable.selectedRow])
        if event.keyCode == 53 { return }
        if event.keyCode == 51 || event.keyCode == 117 {
            propose(nil, forCommand: identifier)
            return
        }
        let characters = event.charactersIgnoringModifiers ?? ""
        guard let first = characters.first, first.isASCII, !first.isWhitespace else { return }
        let binding = MenuShortcutCatalog.menuBinding(
            keyEquivalent: String(first),
            modifierFlags: event.modifierFlags.rawValue
        )
        propose(binding, forCommand: identifier)
    }

    @objc private func clearSelected(_ sender: Any?) {
        guard captureTable.selectedRow >= 0, captureTable.selectedRow < commands.count else { return }
        propose(nil, forCommand: commandID(commands[captureTable.selectedRow]))
    }

    private func propose(_ assignment: [String: Any]?, forCommand identifier: String) {
        let result = MenuShortcutCatalog.proposing(
            assignment: assignment,
            forCommand: identifier,
            currentAssignments: assignments,
            occupiedMenuShortcuts: occupiedMenuShortcuts(),
            viewerHotKeys: UserDefaults.standard.dictionary(forKey: "HOTKEYS") ?? [:]
        )
        if result["accepted"] as? Bool == true {
            assignments = result["assignments"] as? [String: [String: Any]] ?? assignments
            persistAndApply()
            status.stringValue = ""
            captureTable.reloadData()
            return
        }
        let clash = result["conflict"] as? [String: Any] ?? [:]
        status.stringValue = conflictMessage(clash)
    }

    private func persistAndApply() {
        MenuShortcutCatalog.save(assignments, to: .standard)
        if let menu = NSApp.mainMenu {
            MenuShortcutCatalog.apply(assignments, to: menu)
        }
    }

    private func reloadCommands() {
        assignments = MenuShortcutCatalog.assignments(from: .standard)
        commands = MenuShortcutCatalog.assignableCommands(pluginDescriptors: loadedPluginDescriptors())
    }

    private func loadedPluginDescriptors() -> [[String: Any]] {
        guard let manager = NSClassFromString("PluginManager") else { return [] }
        let dictionary = (manager as AnyObject).perform(NSSelectorFromString("pluginsDict"))?.takeUnretainedValue() as? [AnyHashable: Any]
        return MenuShortcutCatalog.pluginDescriptors(fromPluginDictionary: dictionary)
    }

    private func occupiedMenuShortcuts() -> [[String: Any]] {
        guard let menu = NSApp.mainMenu else { return [] }
        return MenuShortcutCatalog.occupiedShortcuts(in: menu)
    }

    private func commandID(_ command: [String: Any]) -> String {
        command["id"] as? String ?? ""
    }

    private func commandTitle(_ command: [String: Any]) -> String {
        let title = command["title"] as? String ?? ""
        if let plugin = command["plugin"] as? String, !plugin.isEmpty, plugin != title {
            return "\(plugin) — \(title)"
        }
        return title
    }

    private func groupLabel(_ group: String?) -> String {
        group == "plugin" ? "Plugin" : "Reconstruction"
    }

    private func conflictMessage(_ clash: [String: Any]) -> String {
        let title = clash["title"] as? String ?? clash["key"] as? String ?? ""
        switch clash["kind"] as? String {
        case "menu":
            return "Conflicts with existing command: \(title)"
        case "assignment":
            return "Conflicts with assigned command: \(title)"
        case "hotkey":
            return "Conflicts with viewer hot key: \(title)"
        default:
            return "Conflicts with an existing command."
        }
    }

    private func buildView() -> NSView {
        let view = NSView(frame: NSRect(x: 0, y: 0, width: 560, height: 420))

        let intro = NSTextField(labelWithString: "Assign shortcuts to reconstructions and plugins. Select a row and press a key; Command is added for a letter. Delete clears. A key already used by another command is refused.")
        intro.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
        intro.lineBreakMode = .byWordWrapping
        intro.usesSingleLineMode = false
        intro.maximumNumberOfLines = 3
        intro.translatesAutoresizingMaskIntoConstraints = false

        captureTable = ShortcutCaptureTable(frame: .zero)
        captureTable.onKey = { [weak self] event in self?.captureKey(event) }
        captureTable.headerView = NSTableHeaderView()
        captureTable.columnAutoresizingStyle = .uniformColumnAutoresizingStyle
        captureTable.allowsEmptySelection = false
        captureTable.usesAlternatingRowBackgroundColors = true
        captureTable.dataSource = self
        captureTable.delegate = self
        addColumn(id: "group", heading: "Group", width: 120)
        addColumn(id: "command", heading: "Command", width: 260)
        addColumn(id: "shortcut", heading: "Shortcut", width: 120)

        let scroll = NSScrollView(frame: .zero)
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.borderType = .bezelBorder
        scroll.documentView = captureTable

        status = NSTextField(labelWithString: "")
        status.textColor = .systemRed
        status.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
        status.translatesAutoresizingMaskIntoConstraints = false

        let clear = NSButton(title: "Clear Shortcut", target: self, action: #selector(clearSelected(_:)))
        clear.bezelStyle = .rounded
        clear.translatesAutoresizingMaskIntoConstraints = false

        view.addSubview(intro)
        view.addSubview(scroll)
        view.addSubview(status)
        view.addSubview(clear)

        NSLayoutConstraint.activate([
            intro.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            intro.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            intro.topAnchor.constraint(equalTo: view.topAnchor, constant: 12),
            scroll.leadingAnchor.constraint(equalTo: intro.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: intro.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: intro.bottomAnchor, constant: 8),
            scroll.heightAnchor.constraint(equalToConstant: 300),
            status.leadingAnchor.constraint(equalTo: intro.leadingAnchor),
            status.trailingAnchor.constraint(equalTo: clear.leadingAnchor, constant: -8),
            status.topAnchor.constraint(equalTo: scroll.bottomAnchor, constant: 8),
            clear.trailingAnchor.constraint(equalTo: intro.trailingAnchor),
            clear.centerYAnchor.constraint(equalTo: status.centerYAnchor),
        ])
        return view
    }

    private func addColumn(id: String, heading: String, width: CGFloat) {
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(id))
        column.title = heading
        column.width = width
        captureTable.addTableColumn(column)
    }
}

private final class ShortcutCaptureTable: NSTableView {
    var onKey: ((NSEvent) -> Void)?

    override func keyDown(with event: NSEvent) {
        onKey?(event)
    }
}
