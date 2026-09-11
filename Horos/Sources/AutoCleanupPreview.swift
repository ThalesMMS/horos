// Read-only inspector for the production database cleanup policy and candidate selection.
import AppKit

@objc(AutoCleanupPreview) public final class AutoCleanupPreview: NSWindowController, NSTableViewDataSource, NSTableViewDelegate {
    // One inspector per process; successive requests update it rather than leaking windows.
    private static let shared = AutoCleanupPreview()
    private let summary = NSTextView()
    private let table = NSTableView()
    private let status = NSTextField(labelWithString: "")
    private let refresh = NSButton(title: NSLocalizedString("Refresh", comment: ""), target: nil, action: nil)
    private var rows: [[String: Any]] = []
    private let formatter: DateFormatter = {
        let f = DateFormatter(); f.dateStyle = .medium; f.timeStyle = .short; return f
    }()

    private init() {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 940, height: 670),
                              styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = NSLocalizedString("Automatic Cleanup Preview", comment: "")
        window.minSize = NSSize(width: 680, height: 520)
        window.isReleasedWhenClosed = false
        super.init(window: window)
        let root = NSView(); window.contentView = root
        summary.isEditable = false; summary.isSelectable = true
        summary.font = .systemFont(ofSize: NSFont.systemFontSize)
        summary.textColor = .textColor; summary.backgroundColor = .textBackgroundColor
        summary.textContainerInset = NSSize(width: 10, height: 10)
        summary.isHorizontallyResizable = false
        summary.textContainer?.widthTracksTextView = true
        let summaryScroll = NSScrollView(); summaryScroll.documentView = summary
        summaryScroll.hasVerticalScroller = true; summaryScroll.borderType = .bezelBorder
        table.usesAlternatingRowBackgroundColors = true
        table.rowHeight = 24
        table.dataSource = self; table.delegate = self
        table.columnAutoresizingStyle = .lastColumnOnlyAutoresizingStyle
        let columns: [(String, String, CGFloat)] = [
            ("rule", NSLocalizedString("Rule", comment: ""), 100),
            ("patient", NSLocalizedString("Patient", comment: ""), 170),
            ("study", NSLocalizedString("Study", comment: ""), 215),
            ("date", NSLocalizedString("Date Acquired", comment: ""), 160),
            ("uid", NSLocalizedString("Study Instance UID", comment: ""), 260)
        ]
        for (key, title, width) in columns {
            let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(key))
            column.title = title; column.width = width; column.minWidth = 80
            table.addTableColumn(column)
        }
        let tableScroll = NSScrollView(); tableScroll.documentView = table
        tableScroll.hasVerticalScroller = true; tableScroll.hasHorizontalScroller = true
        tableScroll.borderType = .bezelBorder
        status.lineBreakMode = .byTruncatingTail
        for view in [summaryScroll, tableScroll, status, refresh] {
            view.translatesAutoresizingMaskIntoConstraints = false; root.addSubview(view)
        }
        NSLayoutConstraint.activate([
            summaryScroll.topAnchor.constraint(equalTo: root.topAnchor, constant: 16),
            summaryScroll.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 16),
            summaryScroll.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -16),
            summaryScroll.heightAnchor.constraint(equalTo: root.heightAnchor, multiplier: 0.43),
            tableScroll.topAnchor.constraint(equalTo: summaryScroll.bottomAnchor, constant: 12),
            tableScroll.leadingAnchor.constraint(equalTo: summaryScroll.leadingAnchor),
            tableScroll.trailingAnchor.constraint(equalTo: summaryScroll.trailingAnchor),
            tableScroll.bottomAnchor.constraint(equalTo: refresh.topAnchor, constant: -12),
            refresh.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -16),
            refresh.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -12),
            status.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 16),
            status.centerYAnchor.constraint(equalTo: refresh.centerYAnchor),
            status.trailingAnchor.constraint(lessThanOrEqualTo: refresh.leadingAnchor, constant: -12)
        ])
        window.center()
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    @objc public static func beginLoading(target: AnyObject, action: Selector) {
        precondition(Thread.isMainThread)
        shared.refresh.target = target; shared.refresh.action = action; shared.refresh.isEnabled = false
        shared.summary.string = NSLocalizedString("Reading cleanup rules and eligible studies…", comment: "")
        shared.status.stringValue = NSLocalizedString("No files will be changed.", comment: "")
        shared.rows = []; shared.table.reloadData()
        shared.showWindow(nil); shared.window?.makeKeyAndOrderFront(nil)
    }

    @objc public static func display(snapshot: [String: Any]) {
        precondition(Thread.isMainThread)
        shared.summary.string = snapshot["summary"] as? String ?? ""
        shared.rows = snapshot["rows"] as? [[String: Any]] ?? []
        shared.table.reloadData()
        shared.status.stringValue = String(format: NSLocalizedString("%ld candidates • Updated %@ • Read only", comment: ""),
                                           shared.rows.count, shared.formatter.string(from: Date()))
        if snapshot["error"] as? Bool == true {
            shared.status.stringValue = NSLocalizedString("Preview unavailable • No files changed", comment: "")
        }
        shared.refresh.isEnabled = true
    }

    public func numberOfRows(in tableView: NSTableView) -> Int { rows.count }
    public func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        guard let key = tableColumn?.identifier.rawValue else { return nil }
        let value = rows[row][key]
        let text = value as? Date != nil ? formatter.string(from: value as! Date) : value as? String ?? ""
        let cell = NSTextField(labelWithString: text)
        cell.lineBreakMode = .byTruncatingTail; cell.toolTip = text
        return cell
    }
}
