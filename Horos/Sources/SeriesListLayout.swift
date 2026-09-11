import AppKit

/// Where the viewer's series list sits (#380 D). The list is the strip of
/// series thumbnails beside the image; it can dock on any edge, and the choice
/// is a preference so it survives a relaunch.
@objc(HorosSeriesListPlacement)
public enum SeriesListPlacement: Int {
    case left = 0
    case right
    case top
    case bottom

    /// Top and bottom lay the strip across the window, so the split view
    /// divides horizontally and the thumbnails run in one row.
    public var isHorizontalStrip: Bool { self == .top || self == .bottom }
    /// Left and top keep the dock before the image pane.
    public var docksFirst: Bool { self == .left || self == .top }

    static let names: [SeriesListPlacement: String] = [.left: "left", .right: "right", .top: "top", .bottom: "bottom"]
    public var name: String { SeriesListPlacement.names[self] ?? "left" }
}

/// The floating panel borrows the existing scroll view. Its dock stays in the
/// split view so moving the list never removes the image pane's sibling.
@MainActor
@objc(HorosSeriesListLayout)
public final class SeriesListLayout: NSObject {
    /// Posted when the placement changes, so open viewers re-place their list.
    @objc public static let placementDidChangeNotification = "HorosSeriesListPlacementDidChange"
    /// The preference the placement is stored under.
    @objc public static let placementDefaultsKey = "HorosSeriesListPlacement"

    @objc(placementNamed:) public static func placement(named name: String) -> SeriesListPlacement {
        SeriesListPlacement.names.first { $0.value == name.lowercased() }?.key ?? .left
    }

    @objc(nameOfPlacement:) public static func name(of placement: SeriesListPlacement) -> String {
        placement.name
    }

    /// The stored choice, defaulting to the historical left dock.
    @objc(storedPlacementIn:) public static func storedPlacement(in defaults: UserDefaults) -> SeriesListPlacement {
        placement(named: defaults.string(forKey: placementDefaultsKey) ?? "left")
    }

    @objc(storePlacement:in:) public static func store(_ placement: SeriesListPlacement, in defaults: UserDefaults) {
        defaults.set(placement.name, forKey: placementDefaultsKey)
    }

    @objc(placeScrollView:inSplitView:floating:visible:thumbnailWidth:)
    public static func place(_ scrollView: NSScrollView, in splitView: NSSplitView,
                             floating: Bool, visible: Bool, thumbnailWidth: CGFloat) {
        place(scrollView, in: splitView, floating: floating, visible: visible,
              thumbnailWidth: thumbnailWidth, placement: .left)
    }

    @objc(placeScrollView:inSplitView:floating:visible:thumbnailWidth:placement:)
    public static func place(_ scrollView: NSScrollView, in splitView: NSSplitView,
                             floating: Bool, visible: Bool, thumbnailWidth: CGFloat,
                             placement: SeriesListPlacement) {
        guard splitView.subviews.count == 2 else { return }
        // The dock is wherever the list already lives; before the first
        // placement it is the historical first subview. The other pane is the
        // image, and it is never removed.
        let dock = scrollView.superview.flatMap { splitView.subviews.contains($0) ? $0 : nil }
            ?? splitView.subviews[0]
        guard dock !== scrollView, let image = splitView.subviews.first(where: { $0 !== dock }) else { return }
        // Moving the dock to the other edge is a reorder of the same two
        // subviews: the image pane is never removed, so its content survives.
        if (placement.docksFirst && splitView.subviews.first !== dock)
            || (!placement.docksFirst && splitView.subviews.last !== dock) {
            let keptDelegate = splitView.delegate
            splitView.delegate = nil
            dock.removeFromSuperview()
            if placement.docksFirst { splitView.addSubview(dock, positioned: .below, relativeTo: image) }
            else { splitView.addSubview(dock, positioned: .above, relativeTo: image) }
            splitView.delegate = keptDelegate
        }
        splitView.isVertical = !placement.isHorizontalStrip

        // Restore the borrowed view before calling this method. Keeping the
        // document view intact preserves its cells and selection.
        let delegate = splitView.delegate
        splitView.delegate = nil
        defer { splitView.delegate = delegate }
        if scrollView.superview !== dock { dock.addSubview(scrollView) }
        scrollView.translatesAutoresizingMaskIntoConstraints = true
        scrollView.autoresizingMask = [.width, .height]
        scrollView.isHidden = false
        dock.isHidden = floating || !visible
        let thickness: CGFloat = floating || !visible ? 0 : thumbnailWidth
        if placement.isHorizontalStrip {
            dock.setFrameSize(NSSize(width: splitView.bounds.width, height: thickness))
            // A horizontal strip scrolls sideways; its thumbnails keep their
            // size, so the scroller has to appear rather than the cells shrink.
            scrollView.hasHorizontalScroller = true
            scrollView.hasVerticalScroller = false
        } else {
            dock.setFrameSize(NSSize(width: thickness, height: splitView.bounds.height))
            scrollView.hasHorizontalScroller = false
            scrollView.hasVerticalScroller = true
        }
        scrollView.frame = dock.bounds
        splitView.dividerStyle = floating ? .thin : .thick
    }

    /// Lays the thumbnails along the strip: one column down the side, one row
    /// across the top or bottom. The cell size never changes, so a strip that
    /// is too short scrolls instead of squeezing its thumbnails.
    @objc(layOutMatrix:count:placement:)
    public static func layOut(_ matrix: NSMatrix, count: Int, placement: SeriesListPlacement) {
        // An autosizing matrix divides its width among its cells: turning a
        // column into a row would halve every thumbnail. The cells keep the
        // size their own class asks for and the strip scrolls instead.
        matrix.autosizesCells = false
        if let cell = matrix.cells.first, cell.cellSize.width > 0, cell.cellSize.height > 0 {
            matrix.cellSize = cell.cellSize
        }
        let rows = placement.isHorizontalStrip ? min(count, 1) : count
        let columns = placement.isHorizontalStrip ? count : min(count, 1)
        if matrix.numberOfRows != rows || matrix.numberOfColumns != columns {
            matrix.renewRows(rows, columns: columns)
        }
        matrix.sizeToCells()
    }

    /// How thick the strip has to be on a given edge: a thumbnail's width down
    /// a side, a thumbnail's height plus the horizontal scroller across the top
    /// or bottom, so a full thumbnail fits instead of being clipped.
    @objc(thicknessForPlacement:thumbnailWidth:thumbnailHeight:)
    public static func thickness(for placement: SeriesListPlacement, thumbnailWidth: CGFloat, thumbnailHeight: CGFloat) -> CGFloat {
        guard placement.isHorizontalStrip else { return thumbnailWidth }
        let scroller = NSScroller.scrollerWidth(for: .regular, scrollerStyle: NSScroller.preferredScrollerStyle)
        return thumbnailHeight + (NSScroller.preferredScrollerStyle == .legacy ? scroller : 0)
    }

    /// The two panes' frames for a given edge and strip thickness. The host's
    /// split-view delegate used to assume a left dock and a vertical divider.
    @objc(resizeSubviewsOfSplitView:placement:thickness:)
    public static func resizeSubviews(of splitView: NSSplitView, placement: SeriesListPlacement, thickness: CGFloat) {
        guard splitView.subviews.count == 2 else { return }
        let dock = splitView.subviews[placement.docksFirst ? 0 : 1]
        guard let image = splitView.subviews.first(where: { $0 !== dock }) else { return }
        let bounds = splitView.bounds
        let divider = thickness > 0 ? splitView.dividerThickness : 0
        guard bounds.width.isFinite, bounds.height.isFinite, bounds.width >= 0, bounds.height >= 0 else { return }
        switch placement {
        case .left:
            dock.frame = NSRect(x: 0, y: 0, width: thickness, height: bounds.height)
            image.frame = NSRect(x: thickness + divider, y: 0, width: max(0, bounds.width - thickness - divider), height: bounds.height)
        case .right:
            image.frame = NSRect(x: 0, y: 0, width: max(0, bounds.width - thickness - divider), height: bounds.height)
            dock.frame = NSRect(x: max(0, bounds.width - thickness), y: 0, width: thickness, height: bounds.height)
        case .top:
            // AppKit's split view stacks its first subview at the top.
            dock.frame = NSRect(x: 0, y: 0, width: bounds.width, height: thickness)
            image.frame = NSRect(x: 0, y: thickness + divider, width: bounds.width, height: max(0, bounds.height - thickness - divider))
        case .bottom:
            image.frame = NSRect(x: 0, y: 0, width: bounds.width, height: max(0, bounds.height - thickness - divider))
            dock.frame = NSRect(x: 0, y: max(0, bounds.height - thickness), width: bounds.width, height: thickness)
        }
    }

    /// Whether the list is showing: the dock's own thickness along the strip's
    /// axis, whichever edge it is on.
    @objc(isListVisibleInSplitView:placement:thickness:)
    public static func isListVisible(in splitView: NSSplitView, placement: SeriesListPlacement, thickness: CGFloat) -> Bool {
        guard splitView.subviews.count == 2 else { return false }
        let dock = splitView.subviews[placement.docksFirst ? 0 : 1]
        if dock.isHidden { return false }
        return (placement.isHorizontalStrip ? dock.frame.height : dock.frame.width) >= thickness
    }
}
