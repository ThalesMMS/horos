import AppKit

/// The notices a DICOM network failure leaves: newest first, a repeat of the one
/// already listed counted on it instead of listed again, at most `capacity` kept.
struct NetworkNoticeLog {
    struct Entry: Equatable {
        let title: String
        let message: String
        var count: Int
        var last: Date
    }

    private(set) var entries: [Entry] = []
    let capacity: Int

    init(capacity: Int = 50) { self.capacity = capacity }

    mutating func add(title: String, message: String, at date: Date) {
        if let index = entries.firstIndex(where: { $0.title == title && $0.message == message }) {
            var entry = entries.remove(at: index)
            entry.count += 1
            entry.last = date
            entries.insert(entry, at: 0)
        } else {
            entries.insert(Entry(title: title, message: message, count: 1, last: date), at: 0)
            if entries.count > capacity { entries.removeLast(entries.count - capacity) }
        }
    }

    mutating func clear() { entries.removeAll() }

    func text(formatter: DateFormatter) -> String {
        entries.map { entry in
            var head = "\(formatter.string(from: entry.last))  \(entry.title)"
            if entry.count > 1 {
                head += "  " + String(format: NSLocalizedString("(%d times)", comment: "network notice repeat count"), entry.count)
            }
            return head + "\n" + entry.message
        }.joined(separator: "\n\n")
    }
}

/// Where a DICOM network failure is said. It used to be a modal alert: while it
/// was open the main run loop ran only in the modal mode, so what the import hands
/// to the main thread waited, and the interface and the import stopped until the
/// alert was dismissed - once per retrieve of an instance the server cannot send
/// (#691). The notices gather in a panel that never becomes key or main.
@objc(HorosNetworkNotices)
public final class NetworkNotices: NSObject {
    private static var log = NetworkNoticeLog()
    private static var panel: NSPanel?
    private static var textView: NSTextView?
    private static let formatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .medium
        return formatter
    }()

    /// Adds a notice and shows the panel without taking focus. Any thread.
    @objc(postTitle:message:)
    public static func post(title: String, message: String) {
        let date = Date()
        DispatchQueue.main.async {
            log.add(title: title, message: message, at: date)
            show()
        }
    }

    /// How many distinct notices are listed. Main thread.
    @objc public static var noticeCount: Int { log.entries.count }

    /// Whether the panel is on screen. Main thread.
    @objc public static var isShowing: Bool { panel?.isVisible ?? false }

    private static func show() {
        let panel = self.panel ?? makePanel()
        textView?.string = log.text(formatter: formatter)
        textView?.scrollToBeginningOfDocument(nil)
        if !panel.isVisible { panel.orderFront(nil) }
    }

    @objc private static func clear(_ sender: Any?) {
        log.clear()
        textView?.string = ""
        panel?.orderOut(nil)
    }

    private static func makePanel() -> NSPanel {
        let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 480, height: 220),
                            styleMask: [.titled, .closable, .resizable, .utilityWindow, .nonactivatingPanel],
                            backing: .buffered, defer: true)
        panel.title = NSLocalizedString("Network Notices", comment: "title of the DICOM network notices panel")
        panel.isFloatingPanel = false
        panel.hidesOnDeactivate = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.isReleasedWhenClosed = false
        panel.setFrameAutosaveName("HorosNetworkNotices")

        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.translatesAutoresizingMaskIntoConstraints = false
        let text = NSTextView()
        text.isEditable = false
        text.isRichText = false
        text.font = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)
        text.autoresizingMask = [.width]
        text.textContainerInset = NSSize(width: 6, height: 6)
        scroll.documentView = text

        let clear = NSButton(title: NSLocalizedString("Clear", comment: "empties the network notices panel"),
                             target: self, action: #selector(clear(_:)))
        clear.controlSize = .small
        clear.translatesAutoresizingMaskIntoConstraints = false

        let content = panel.contentView!
        content.addSubview(scroll)
        content.addSubview(clear)
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: content.topAnchor),
            scroll.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            clear.topAnchor.constraint(equalTo: scroll.bottomAnchor, constant: 6),
            clear.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -8),
            clear.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -6),
        ])
        if !panel.setFrameUsingName("HorosNetworkNotices") { panel.center() }
        self.panel = panel
        self.textView = text
        return panel
    }
}
