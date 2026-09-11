import Foundation
import CoreGraphics
import AppKit

@objc(HorosROILabelPresentation)
public final class ROILabelPresentation: NSObject {
    /// Preserve the renderer's formatted value/units rather than recalculating
    /// geometry or imposing a second locale/precision policy.
    @objc(compactMeasurement:primaryAngle:)
    public static func compactMeasurement(_ line: String?, primaryAngle: Bool) -> String? {
        guard let line, let colon = line.firstIndex(of: ":") else { return nil }
        var value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespacesAndNewlines)
        if primaryAngle, let separator = value.range(of: " / ") {
            value = String(value[..<separator.lowerBound])
        }
        guard let first = value.unicodeScalars.first,
              CharacterSet.decimalDigits.contains(first) || "+-−".unicodeScalars.contains(first) else { return nil }
        // Compound ultrasound measurements (X/Y) and unknown labels fall back
        // to the complete presentation instead of losing directional context.
        return value
    }
    /// Keep the label at the nearest viewport edge when its image anchor
    /// leaves the screen. Oversized labels retain their metrics and start at
    /// the viewport's leading/top edge; the renderer must not shrink text.
    @objc(constrainLabelRect:toViewport:)
    public static func constrainLabelRect(_ rect: NSRect, toViewport viewport: NSRect) -> NSRect {
        guard [rect.origin.x, rect.origin.y, rect.width, rect.height,
               viewport.origin.x, viewport.origin.y, viewport.width, viewport.height].allSatisfy({ $0.isFinite }),
              rect.width >= 0, rect.height >= 0, viewport.width > 0, viewport.height > 0 else { return rect }
        var result = rect
        result.origin.x = min(max(rect.minX, viewport.minX), max(viewport.minX, viewport.maxX - rect.width))
        result.origin.y = min(max(rect.minY, viewport.minY), max(viewport.minY, viewport.maxY - rect.height))
        return result
    }
    @objc(placeLabelRect:inViewport:avoiding:)
    public static func placeLabelRect(_ rect: NSRect, inViewport viewport: NSRect, avoiding values: [NSValue]) -> NSRect {
        let desired = constrainLabelRect(rect, toViewport: viewport)
        let obstacles = values.map { $0.rectValue }.filter { !$0.isEmpty && !$0.isInfinite && !$0.isNull }
        var candidates = [desired]
        for obstacle in obstacles {
            for y in [obstacle.minY - rect.height - 2, obstacle.maxY + 2] {
                candidates.append(constrainLabelRect(NSRect(x: desired.minX, y: y, width: rect.width, height: rect.height), toViewport: viewport))
            }
            for x in [obstacle.minX - rect.width - 2, obstacle.maxX + 2] {
                candidates.append(constrainLabelRect(NSRect(x: x, y: desired.minY, width: rect.width, height: rect.height), toViewport: viewport))
            }
        }
        func overlap(_ candidate: NSRect) -> CGFloat {
            obstacles.reduce(0) { sum, obstacle in
                let intersection = candidate.intersection(obstacle)
                return sum + (intersection.isNull ? 0 : intersection.width * intersection.height)
            }
        }
        // The axis-only candidates can miss free diagonal regions. Sweep the
        // vertical obstacle boundaries and project the desired x onto free
        // intervals at each height, without searching individual pixels.
        if overlap(desired) == 0 { return desired }
        if rect.width <= viewport.width && rect.height <= viewport.height {
            let minX = viewport.minX, maxX = viewport.maxX - rect.width
            let minY = viewport.minY, maxY = viewport.maxY - rect.height
            var heights: Set<CGFloat> = [desired.minY, minY, maxY]
            for obstacle in obstacles {
                heights.insert(min(max(obstacle.minY - rect.height - 2, minY), maxY))
                heights.insert(min(max(obstacle.maxY + 2, minY), maxY))
            }
            for y in heights.sorted() {
                let intervals = obstacles.filter { y < $0.maxY + 2 && y + rect.height > $0.minY - 2 }
                    .map { ($0.minX - rect.width - 2, $0.maxX + 2) }
                    .sorted { $0.0 < $1.0 }
                var cursor = minX
                var nearest: CGFloat?
                func consider(_ lower: CGFloat, _ upper: CGFloat) {
                    guard lower <= upper else { return }
                    let x = min(max(desired.minX, lower), upper)
                    if nearest == nil || abs(x - desired.minX) < abs(nearest! - desired.minX) { nearest = x }
                }
                for interval in intervals {
                    if interval.1 < cursor { continue }
                    if interval.0 > maxX { break }
                    if interval.0 >= cursor { consider(cursor, min(interval.0, maxX)) }
                    cursor = max(cursor, interval.1)
                    if cursor > maxX { break }
                }
                consider(cursor, maxX)
                if let x = nearest { candidates.append(NSRect(x: x, y: y, width: rect.width, height: rect.height)) }
            }
        }
        var best = desired
        var bestOverlap = overlap(best)
        var bestDistance: CGFloat = 0
        for candidate in candidates.dropFirst() {
            let area = overlap(candidate)
            let distance = pow(candidate.minX - desired.minX, 2) + pow(candidate.minY - desired.minY, 2)
            if area < bestOverlap || (area == bestOverlap && distance < bestDistance) {
                best = candidate; bestOverlap = area; bestDistance = distance
            }
        }
        return best
    }
    @objc(hasUnoccupiedPlacementForLabelRect:inViewport:avoiding:)
    public static func hasUnoccupiedPlacement(forLabelRect rect: NSRect, inViewport viewport: NSRect, avoiding values: [NSValue]) -> Bool {
        let placed = placeLabelRect(rect, inViewport: viewport, avoiding: values)
        return viewport.contains(placed) && !values.contains { value in
            let obstacle = value.rectValue
            return !obstacle.isEmpty && !obstacle.isInfinite && !obstacle.isNull && placed.intersects(obstacle)
        }
    }

    private static let wrappedTextCache: NSCache<NSArray, NSArray> = {
        let cache = NSCache<NSArray, NSArray>()
        cache.countLimit = 512
        return cache
    }()

    /// Empty strings do not advance the legacy renderer's line counter.
    /// Reserve an explicit overflow line without modifying the source label.
    @objc(fitLines:maximumLineCount:)
    public static func fitLines(_ lines: [String], maximumLineCount: Int) -> [String] {
        let visible = lines.filter { !$0.isEmpty }
        guard visible.count > maximumLineCount else { return lines }
        // Keep an indication even when a pane cannot accommodate one line.
        let count = max(1, maximumLineCount)
        return Array(visible.prefix(count - 1)) + ["…"]
    }

    @objc(showLabels:inWindow:)
    public static func showLabels(_ labels: [[String]], inWindow window: NSWindow) {
        let alert = NSAlert()
        alert.messageText = NSLocalizedString("ROI Labels", comment: "Complete ROI label text")
        alert.informativeText = NSLocalizedString("Complete labels for the current image.", comment: "ROI label sheet description")
        alert.addButton(withTitle: NSLocalizedString("Close", comment: "Close ROI labels"))
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 480, height: 300))
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        let text = NSTextView(frame: scroll.contentView.bounds)
        text.isEditable = false
        text.isSelectable = true
        text.font = NSFont.systemFont(ofSize: NSFont.systemFontSize)
        text.textColor = .textColor
        text.backgroundColor = .textBackgroundColor
        text.isVerticallyResizable = true
        text.isHorizontallyResizable = false
        text.autoresizingMask = [.width]
        text.textContainer?.widthTracksTextView = true
        text.textContainer?.containerSize = NSSize(width: scroll.contentSize.width, height: .greatestFiniteMagnitude)
        text.string = labels.map { $0.filter { !$0.isEmpty }.joined(separator: "\n") }
            .filter { !$0.isEmpty }.joined(separator: "\n\n")
        scroll.documentView = text
        alert.accessoryView = scroll
        alert.beginSheetModal(for: window)
    }

    @objc(wrapLines:font:maximumWidth:)
    public static func wrapLines(_ lines: [String], font: NSFont, maximumWidth: CGFloat) -> [String] {
        guard maximumWidth.isFinite, maximumWidth > 0 else { return lines }
        let key = [lines as NSArray, font, NSNumber(value: Double(maximumWidth))] as NSArray
        if let cached = wrappedTextCache.object(forKey: key) { return cached as! [String] }
        let attributes: [NSAttributedString.Key: Any] = [.font: font]
        func fits(_ text: String) -> Bool {
            text.utf16.count <= 300 && (text as NSString).size(withAttributes: attributes).width <= maximumWidth
        }
        var result: [String] = []
        for line in lines {
            for paragraph in line.components(separatedBy: "\n") {
                var remaining = paragraph
                while !remaining.isEmpty && !fits(remaining) {
                    var end = remaining.startIndex
                    var wordBoundary: String.Index?
                    var next = end
                    while next < remaining.endIndex {
                        let after = remaining.index(after: next)
                        if !fits(String(remaining[..<after])) { break }
                        end = after
                        if remaining[next].isWhitespace { wordBoundary = after }
                        next = after
                    }
                    // Never split a composed character, even if one glyph is wider than the pane.
                    if end == remaining.startIndex { end = remaining.index(after: end) }
                    let cut = wordBoundary ?? end
                    result.append(String(remaining[..<cut]))
                    remaining = String(remaining[cut...])
                }
                result.append(remaining)
            }
        }
        wrappedTextCache.setObject(result as NSArray, forKey: key)
        return result
    }
}
