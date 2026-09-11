#!/usr/bin/env python3
"""Exercise the production Swift dock with real AppKit views and selections."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
driver = r'''
import AppKit

@main struct Check {
    @MainActor static func main() {
        NSApplication.shared.setActivationPolicy(.prohibited)
        func check(_ value: Bool, _ message: String) {
            if !value { fputs("FAIL: \(message)\n", stderr); exit(1) }
        }
        func viewer(selected: Int) -> (NSSplitView, NSView, NSScrollView, NSMatrix) {
            let split = NSSplitView(frame: NSRect(x: 0, y: 0, width: 800, height: 300))
            split.isVertical = true
            let dock = NSView(frame: NSRect(x: 0, y: 0, width: 100, height: 300))
            let image = NSView(frame: NSRect(x: 109, y: 0, width: 691, height: 300))
            split.addSubview(dock); split.addSubview(image)
            let scroll = NSScrollView(frame: dock.bounds)
            let matrix = NSMatrix(frame: NSRect(x: 0, y: 0, width: 100, height: 800),
                                  mode: .radioModeMatrix, prototype: NSButtonCell(),
                                  numberOfRows: 8, numberOfColumns: 1)
            matrix.cellSize = NSSize(width: 100, height: 100)
            for (index, cell) in matrix.cells.enumerated() {
                cell.title = index == 0 ? "Hide Series" : "Series \(index)"
                cell.representedObject = NSNumber(value: index)
            }
            matrix.selectCell(atRow: selected, column: 0)
            scroll.documentView = matrix
            return (split, image, scroll, matrix)
        }
        let a = viewer(selected: 3), b = viewer(selected: 5)
        let viewers = [a, b]
        let panels = [NSView(frame: NSRect(x: 0, y: 0, width: 110, height: 500)),
                      NSView(frame: NSRect(x: 0, y: 0, width: 110, height: 700))]
        let docks = viewers.map { $0.0.subviews[0] }
        let cells = viewers.map { $0.3.cells }
        for cycle in 0..<20 {
            for index in 0..<viewers.count {
                let (split, image, scroll, matrix) = viewers[index]
                SeriesListLayout.place(scroll, in: split, floating: false,
                                       visible: true, thumbnailWidth: 100)
                check(split.subviews.count == 2 && split.subviews[1] === image,
                      "image pane order survives docking")
                check(scroll.superview === docks[index] && !docks[index].isHidden &&
                      scroll.frame == docks[index].bounds, "docked list fills its container")
                check(matrix.cells.elementsEqual(cells[index], by: { $0 === $1 }) &&
                      matrix.selectedRow == (index == 0 ? 3 : 5), "cells and selection survive")
                // Global Series List off/on is independent of the study header.
                SeriesListLayout.place(scroll, in: split, floating: false,
                                       visible: false, thumbnailWidth: 100)
                check(docks[index].isHidden && matrix.numberOfRows == 8, "hide retains rows")
                SeriesListLayout.place(scroll, in: split, floating: true,
                                       visible: true, thumbnailWidth: 100)
                check(docks[index].isHidden && split.subviews.count == 2,
                      "floating mode leaves the dock in place")
                // The panel borrows the scroll view, just as setThumbnailsView does.
                panels[index].addSubview(scroll); scroll.frame = panels[index].bounds
                check(scroll.superview === panels[index] && split.subviews[1] === image,
                      "one independent borrowed list per panel")
                check(matrix.selectedRow == (index == 0 ? 3 : 5), "floating selection survives")
            }
            // Focus on a second viewer on the same display swaps borrowed lists.
            docks[0].addSubview(a.2)
            panels[0].addSubview(b.2)
            check(a.2.superview === docks[0] && b.2.superview === panels[0], "same-screen owner swap")
            // Return all panels before changing the preference, including a moved owner.
            docks[1].addSubview(b.2)
            for (index, v) in viewers.enumerated() {
                SeriesListLayout.place(v.2, in: v.0, floating: false,
                                       visible: cycle % 2 == 0, thumbnailWidth: 100)
                check(v.2.superview === docks[index] && v.2.documentView === v.3,
                      "same document restored after return")
            }
        }
        // A viewer that starts in shared mode must dock without reconstructing cells.
        let fresh = viewer(selected: 7)
        SeriesListLayout.place(fresh.2, in: fresh.0, floating: true,
                               visible: true, thumbnailWidth: 100)
        panels[0].addSubview(fresh.2)
        fresh.0.subviews[0].addSubview(fresh.2)
        SeriesListLayout.place(fresh.2, in: fresh.0, floating: false,
                               visible: true, thumbnailWidth: 100)
        check(fresh.3.selectedRow == 7 && fresh.3.numberOfRows == 8, "initial floating mode")
        // #380 D: the strip docks on any edge, keeps its cells and its
        // selection, and a horizontal strip lays the thumbnails in one row.
        let placements: [(SeriesListPlacement, Bool, Bool)] = [(.left, false, true), (.right, false, false),
                                                               (.top, true, true), (.bottom, true, false)]
        let edge = viewer(selected: 2)
        let edgeDock = edge.0.subviews[0], edgeImage = edge.1
        let cellsBefore = edge.3.cells
        SeriesListLayout.layOut(edge.3, count: 8, placement: .left)
        let firstCellSize = edge.3.cellSize
        for (placement, horizontal, first) in placements {
            SeriesListLayout.place(edge.2, in: edge.0, floating: false, visible: true,
                                   thumbnailWidth: 100, placement: placement)
            SeriesListLayout.layOut(edge.3, count: 8, placement: placement)
            let dock = edge.2.superview!
            check(edge.0.subviews.count == 2, "\(placement.name): still two panes")
            check(edge.0.isVertical == !horizontal, "\(placement.name): split view orientation")
            check((edge.0.subviews.first === dock) == first, "\(placement.name): dock edge")
            check(edge.0.subviews.contains(edgeImage), "\(placement.name): the image pane is never removed")
            check(dock === edgeDock, "\(placement.name): the same dock moves, not a new one")
            check(!dock.isHidden && edge.2.frame == dock.bounds, "\(placement.name): the list fills its dock")
            check(edge.3.cells.elementsEqual(cellsBefore, by: { $0 === $1 }), "\(placement.name): cells survive")
            // renewRows: keeps the cells but not the selected index; the host
            // reselects the current series after building the matrix.
            check(edge.3.cells.count == 8, "\(placement.name): the cell count survives")
            // NSButtonCell answers its own size; what matters is that turning a
            // column into a row does not change it.
            check(edge.3.cellSize == firstCellSize, "\(placement.name): thumbnails keep their size")
            check(!edge.3.autosizesCells, "\(placement.name): the matrix does not divide its width among the cells")
            if horizontal {
                check(edge.3.numberOfRows == 1 && edge.3.numberOfColumns == 8, "\(placement.name): one row across")
                check(edge.2.hasHorizontalScroller && !edge.2.hasVerticalScroller, "\(placement.name): scrolls sideways")
                check(dock.frame.height == 100 && dock.frame.width == edge.0.bounds.width, "\(placement.name): strip across the window")
                check(edge.3.frame.width >= firstCellSize.width * 8,
                      "\(placement.name): the row is at least eight thumbnails wide (\(edge.3.frame.width) vs \(firstCellSize.width * 8)), so a narrow strip scrolls instead of shrinking them")
            } else {
                check(edge.3.numberOfRows == 8 && edge.3.numberOfColumns == 1, "\(placement.name): one column down")
                check(edge.2.hasVerticalScroller && !edge.2.hasHorizontalScroller, "\(placement.name): scrolls down")
                check(dock.frame.width == 100 && dock.frame.height == edge.0.bounds.height, "\(placement.name): strip down the window")
            }
        }
        // The split view's two panes, on every edge, at the thickness the host asks for.
        for (placement, horizontal, first) in placements {
            SeriesListLayout.place(edge.2, in: edge.0, floating: false, visible: true,
                                   thumbnailWidth: 100, placement: placement)
            SeriesListLayout.resizeSubviews(of: edge.0, placement: placement, thickness: 100)
            let dock = edge.2.superview!
            let image = edge.0.subviews.first { $0 !== dock }!
            check(!NSIntersectsRect(NSInsetRect(dock.frame, 1, 1), NSInsetRect(image.frame, 1, 1)),
                  "\(placement.name): the panes do not overlap")
            if horizontal {
                check(dock.frame.height == 100 && dock.frame.width == edge.0.bounds.width, "\(placement.name): strip thickness")
                check(image.frame.height == edge.0.bounds.height - 100 - edge.0.dividerThickness, "\(placement.name): image keeps the rest")
                check((dock.frame.origin.y == 0) == first, "\(placement.name): the dock is on its edge")
            } else {
                check(dock.frame.width == 100 && dock.frame.height == edge.0.bounds.height, "\(placement.name): strip thickness")
                check(image.frame.width == edge.0.bounds.width - 100 - edge.0.dividerThickness, "\(placement.name): image keeps the rest")
                check((dock.frame.origin.x == 0) == first, "\(placement.name): the dock is on its edge")
            }
            check(SeriesListLayout.isListVisible(in: edge.0, placement: placement, thickness: 100),
                  "\(placement.name): a strip of full thickness counts as visible")
            SeriesListLayout.resizeSubviews(of: edge.0, placement: placement, thickness: 0)
            check(!SeriesListLayout.isListVisible(in: edge.0, placement: placement, thickness: 100),
                  "\(placement.name): a collapsed strip counts as hidden")
        }

        // The stored choice round-trips through a preference domain.
        let defaults = UserDefaults(suiteName: "org.horos.test.serieslist.\(UUID().uuidString)")!
        check(SeriesListLayout.storedPlacement(in: defaults) == .left, "the default placement is the historical left dock")
        for (placement, _, _) in placements {
            SeriesListLayout.store(placement, in: defaults)
            check(SeriesListLayout.storedPlacement(in: defaults) == placement, "\(placement.name) survives a restart")
            check(SeriesListLayout.placement(named: placement.name) == placement, "\(placement.name) round-trips by name")
        }
        defaults.set("nonsense", forKey: SeriesListLayout.placementDefaultsKey)
        check(SeriesListLayout.storedPlacement(in: defaults) == .left, "an unknown placement falls back to the left dock")

        print("PASS: 20 two-viewer mode cycles, stable panes/cells/selection, hide/show, panel swaps, floating startup, and the four dock edges with their row/column layout and stored choice")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-series-list-mode-') as folder:
    folder = Path(folder)
    (folder/'Check.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5',
                    str(root/'Horos/Sources/SeriesListLayout.swift'), str(folder/'Check.swift'),
                    '-o', str(folder/'check')], check=True)
    subprocess.run([str(folder/'check')], check=True)
