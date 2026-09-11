import AppKit

/// Layout for the existing database controls; their outlets, bindings and actions stay intact.
@objc(HorosDatabaseBrowserLayout)
public final class DatabaseBrowserLayout: NSObject {
    @objc(prepareFilterView:)
    public static func prepareFilterView(_ view: NSView) {
        guard let popup = view.subviews.first as? NSPopUpButton else { return }
        popup.controlSize = .regular
        popup.font = .systemFont(ofSize: NSFont.systemFontSize)
        popup.translatesAutoresizingMaskIntoConstraints = false
        popup.widthAnchor.constraint(equalToConstant: 124).isActive = true
        installStack([popup], in: view)
    }

    @objc(prepareSearchView:)
    public static func prepareSearchView(_ view: NSView) {
        guard let search = view.subviews.first as? NSSearchField else { return }
        let controls = view.subviews
        search.controlSize = .regular
        search.font = .systemFont(ofSize: NSFont.systemFontSize)
        search.translatesAutoresizingMaskIntoConstraints = false
        let preferredWidth = search.widthAnchor.constraint(equalToConstant: 180)
        preferredWidth.priority = .defaultHigh
        NSLayoutConstraint.activate([
            search.widthAnchor.constraint(greaterThanOrEqualToConstant: 160),
            search.widthAnchor.constraint(lessThanOrEqualToConstant: 280),
            preferredWidth
        ])
        for case let button as NSButton in controls {
            button.controlSize = .small
            button.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
            button.setContentCompressionResistancePriority(.required, for: .horizontal)
        }
        // Soundex and the conditional whole-database result button have their own
        // horizontal space. A toolbar must not compress the old two-row nib layout.
        installStack(controls, in: view)
    }

    private static func installStack(_ controls: [NSView], in view: NSView) {
        let stack = NSStackView(views: controls)
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 8
        stack.detachesHiddenViews = true
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            stack.topAnchor.constraint(equalTo: view.topAnchor),
            stack.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
        view.setFrameSize(stack.fittingSize)
    }

    @objc(prepareSidebar:)
    public static func prepareSidebar(_ split: NSSplitView) {
        // The nib also autosaved this split through AppKit. Use the controller's
        // SplitAlbums geometry only, so a second restore cannot collapse it later.
        split.autosaveName = nil
        for pane in split.subviews {
            let content: NSView
            if let box = pane as? NSBox {
                box.contentViewMargins = .zero
                content = box.contentView ?? box
            } else {
                content = pane
            }
            for case let scroll as NSScrollView in content.subviews {
                scroll.autoresizingMask = [.width, .height]
                scroll.frame = content.bounds
                (scroll as? DatabaseSidebarScrollView)?.reserveHeaderSpace()
            }
        }
    }

    @objc(minimumPaneHeightInSplit:atIndex:)
    public static func minimumPaneHeight(in split: NSSplitView, at index: Int) -> CGFloat {
        guard split.subviews.indices.contains(index) else { return 0 }
        let minima = split.subviews.indices.map { $0 == 0 ? CGFloat(160) : CGFloat(80) }
        let available = max(0, split.bounds.height - CGFloat(split.subviews.count - 1) * split.dividerThickness)
        return minima[index] * min(1, available / minima.reduce(0, +))
    }

    @objc(layoutSidebar:)
    public static func layoutSidebar(_ split: NSSplitView) {
        let panes = split.subviews
        guard !panes.isEmpty else { return }
        let divider = split.dividerThickness
        let available = max(0, split.bounds.height - CGFloat(panes.count - 1) * divider)
        let minima = panes.indices.map { minimumPaneHeight(in: split, at: $0) }
        let extra = max(0, available - minima.reduce(0, +))
        let valid = panes.enumerated().allSatisfy {
            !$0.element.isHidden && $0.element.frame.height.isFinite && $0.element.frame.height >= minima[$0.offset]
        }
        var weights = panes.enumerated().map {
            valid ? max(0, $0.element.frame.height - minima[$0.offset]) : ($0.offset == 0 ? CGFloat(3) : CGFloat(1))
        }
        if weights.reduce(0, +) == 0 { weights = panes.map { _ in 1 } }
        let totalWeight = weights.reduce(0, +)
        var position: CGFloat = 0
        for (index, pane) in panes.enumerated() {
            let end = index == panes.count - 1 ? split.bounds.height :
                (position + minima[index] + extra * weights[index] / totalWeight).rounded()
            pane.isHidden = false
            pane.frame = NSRect(x: 0, y: position, width: max(0, split.bounds.width), height: max(0, end - position))
            position = end + divider
        }
    }
}

/// Keep the column header outside the scrollable rows, including after a saved
/// scroll offset or scrollRowToVisible puts the first album at document origin.
@objc(HorosDatabaseSidebarScrollView)
public final class DatabaseSidebarScrollView: NSScrollView {
    private var reservesHeader = false

    func reserveHeaderSpace() {
        automaticallyAdjustsContentInsets = false
        contentInsets = NSEdgeInsetsZero
        contentView.automaticallyAdjustsContentInsets = false
        contentView.contentInsets = NSEdgeInsetsZero
        reservesHeader = true
        tile()
    }

    public override func tile() {
        super.tile()
        guard reservesHeader, let table = documentView as? NSTableView,
              let header = table.headerView, header.superview != nil else { return }
        let headerFrame = header.convert(header.bounds, to: self)
        var frame = contentView.frame
        guard frame.intersects(headerFrame) else { return }
        if isFlipped {
            let bottom = frame.maxY
            frame.origin.y = min(bottom, headerFrame.maxY)
            frame.size.height = max(0, bottom - frame.minY)
        } else {
            frame.size.height = max(0, min(frame.maxY, headerFrame.minY) - frame.minY)
        }
        contentView.frame = frame
        contentView.scroll(to: contentView.constrainBoundsRect(contentView.bounds).origin)
    }
}
