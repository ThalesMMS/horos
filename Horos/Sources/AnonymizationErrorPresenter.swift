import AppKit

/// Keeps the initial error compact while making every local input result inspectable.
@objc(HorosAnonymizationErrorPresenter)
public final class AnonymizationErrorPresenter: NSObject {
    public static func reportText(_ error: NSError) -> String {
        let rows = error.userInfo["HorosAnonymizationFileResults"] as? [[String: Any]] ?? []
        var sections = [error.localizedDescription]
        for (index, row) in rows.enumerated() {
            let source = row["source"] as? String ?? ""
            let detail = row["detail"] as? String ?? ""
            sections.append("\(index + 1). \(source)\n\(detail)")
        }
        return sections.joined(separator: "\n\n")
    }

    @objc(presentError:)
    public static func present(error supplied: NSError?) {
        guard Thread.isMainThread else {
            DispatchQueue.main.async { present(error: supplied) }
            return
        }
        let error = supplied ?? NSError(domain: "HorosAnonymization", code: 1, userInfo: [
            NSLocalizedDescriptionKey: NSLocalizedString("Anonymization did not produce a complete set of files. The original images have been preserved.", comment: "")
        ])
        let rows = error.userInfo["HorosAnonymizationFileResults"] as? [[String: Any]] ?? []
        let alert = NSAlert()
        alert.messageText = NSLocalizedString("Anonymize Error", comment: "")
        alert.informativeText = error.localizedDescription
        alert.addButton(withTitle: NSLocalizedString("OK", comment: ""))
        if !rows.isEmpty {
            alert.addButton(withTitle: NSLocalizedString("File Results...", comment: ""))
        }
        guard alert.runModal() == .alertSecondButtonReturn else { return }

        let details = NSAlert()
        details.messageText = NSLocalizedString("Anonymization File Results", comment: "")
        details.informativeText = String(format: NSLocalizedString("%ld input files. This report stays on this computer.", comment: ""), rows.count)
        details.addButton(withTitle: NSLocalizedString("OK", comment: ""))
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 680, height: 360))
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        let text = NSTextView(frame: scroll.bounds)
        text.isEditable = false
        text.isSelectable = true
        text.font = .monospacedSystemFont(ofSize: NSFont.smallSystemFontSize, weight: .regular)
        text.textColor = .textColor
        text.backgroundColor = .textBackgroundColor
        text.textContainerInset = NSSize(width: 8, height: 8)
        text.isVerticallyResizable = true
        text.isHorizontallyResizable = false
        text.autoresizingMask = [.width]
        text.textContainer?.widthTracksTextView = true
        text.string = reportText(error)
        text.setAccessibilityLabel(NSLocalizedString("Per-file anonymization results", comment: ""))
        scroll.documentView = text
        details.accessoryView = scroll
        details.runModal()
    }
}
