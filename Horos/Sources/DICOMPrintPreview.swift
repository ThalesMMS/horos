import AppKit

/// The same rendered tile is displayed in the preview and handed to the spool writer.
@objc(HorosDICOMPrintPreview)
public final class DICOMPrintPreview: NSObject, NSWindowDelegate {
    private struct Edit { var zoom = 1.0; var turns = 0; var annotations = false }
    private let plain: [NSImage]
    private let annotated: [NSImage]
    private var edits: [Edit]
    private var rendered: [NSImage]
    private let columns: Int
    private let rows: Int
    private let window: NSWindow
    private let tiles = NSView()
    private let selector = NSPopUpButton()
    private let zoom = NSSlider(value: 1, minValue: 0.25, maxValue: 4, target: nil, action: nil)
    private let annotation = NSButton(checkboxWithTitle: NSLocalizedString("Annotations", comment: ""), target: nil, action: nil)
    private let pageLabel = NSTextField(labelWithString: "")
    private var accepted = false
    private var page = 0
    private var selected = 0
    private var tileButtons: [NSButton] = []

    @objc(initWithImages:annotatedImages:columns:rows:filmSize:landscape:)
    public init(images: [NSImage], annotatedImages: [NSImage], columns: Int, rows: Int, filmSize: String, landscape: Bool) {
        plain = images
        annotated = annotatedImages
        rendered = images
        edits = images.map { _ in Edit() }
        self.columns = max(1, columns)
        self.rows = max(1, rows)
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 920, height: 760), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        super.init()
        window.title = NSLocalizedString("DICOM Print Preview", comment: "")
        window.isReleasedWhenClosed = false
        window.delegate = self
        guard let content = window.contentView else { return }
        let note = NSTextField(labelWithString: NSLocalizedString("Select an image to adjust it. Changes apply only to this print job.", comment: ""))
        note.frame = NSRect(x: 20, y: 720, width: 880, height: 22)
        content.addSubview(note)
        let aspect = Self.filmAspectRatio(filmSize, landscape: landscape)
        let tileHeight = min(CGFloat(570), CGFloat(880) / aspect)
        let tileWidth = tileHeight * aspect
        tiles.frame = NSRect(x: 20 + (880 - tileWidth) / 2, y: 140 + (570 - tileHeight) / 2, width: tileWidth, height: tileHeight)
        content.addSubview(tiles)
        selector.addItems(withTitles: images.indices.map { String(format: NSLocalizedString("Image %d", comment: ""), $0 + 1) })
        selector.frame = NSRect(x: 20, y: 94, width: 155, height: 28)
        selector.target = self; selector.action = #selector(selectImage)
        selector.setAccessibilityLabel(NSLocalizedString("Print image", comment: "")); content.addSubview(selector)
        let zoomLabel = NSTextField(labelWithString: NSLocalizedString("Zoom", comment: ""))
        zoomLabel.frame = NSRect(x: 190, y: 97, width: 50, height: 22); content.addSubview(zoomLabel)
        zoom.frame = NSRect(x: 245, y: 94, width: 180, height: 28)
        zoom.target = self; zoom.action = #selector(changeZoom)
        zoom.setAccessibilityLabel(NSLocalizedString("Print image zoom", comment: "")); content.addSubview(zoom)
        addButton("Rotate 90°", frame: NSRect(x: 440, y: 94, width: 120, height: 28), action: #selector(rotate))
        annotation.frame = NSRect(x: 570, y: 94, width: 160, height: 28)
        annotation.target = self; annotation.action = #selector(changeAnnotations); content.addSubview(annotation)
        addButton("Reset image", frame: NSRect(x: 755, y: 94, width: 145, height: 28), action: #selector(resetImage))
        addButton("Previous page", frame: NSRect(x: 20, y: 36, width: 140, height: 30), action: #selector(previousPage))
        addButton("Next page", frame: NSRect(x: 165, y: 36, width: 140, height: 30), action: #selector(nextPage))
        pageLabel.frame = NSRect(x: 320, y: 39, width: 230, height: 24); content.addSubview(pageLabel)
        addButton("Cancel", frame: NSRect(x: 650, y: 36, width: 115, height: 30), action: #selector(cancel))
        addButton("Print", frame: NSRect(x: 775, y: 36, width: 125, height: 30), action: #selector(confirm))
        refreshPage()
    }

    private func addButton(_ title: String, frame: NSRect, action: Selector) {
        let button = NSButton(title: NSLocalizedString(title, comment: ""), target: self, action: action)
        button.bezelStyle = .rounded; button.frame = frame; window.contentView?.addSubview(button)
    }
    private var perPage: Int { columns * rows }
    private var pageCount: Int { max(1, (plain.count + perPage - 1) / perPage) }

    @objc public func runModal() -> [NSImage]? {
        guard !plain.isEmpty, plain.count == annotated.count else { return nil }
        window.center(); window.makeKeyAndOrderFront(nil)
        NSApp.runModal(for: window)
        window.orderOut(nil)
        return accepted ? rendered : nil
    }
    public func windowShouldClose(_ sender: NSWindow) -> Bool { cancel(); return false }
    @objc private func cancel() { accepted = false; NSApp.stopModal() }
    @objc private func confirm() { accepted = true; NSApp.stopModal() }
    @objc private func previousPage() { page = max(0, page - 1); selected = page * perPage; refreshPage() }
    @objc private func nextPage() { page = min(pageCount - 1, page + 1); selected = page * perPage; refreshPage() }
    @objc private func selectImage() { selected = max(0, selector.indexOfSelectedItem); page = selected / perPage; refreshPage() }
    @objc private func selectTile(_ sender: NSButton) { selected = sender.tag; refreshPage() }
    @objc private func changeZoom() { edits[selected].zoom = zoom.doubleValue; renderSelected() }
    @objc private func rotate() { edits[selected].turns = (edits[selected].turns + 1) % 4; renderSelected() }
    @objc private func changeAnnotations() { edits[selected].annotations = annotation.state == .on; renderSelected() }
    @objc private func resetImage() { edits[selected] = Edit(); renderSelected() }
    private func renderSelected() {
        let edit = edits[selected]
        rendered[selected] = Self.render(edit.annotations ? annotated[selected] : plain[selected], zoom: edit.zoom, quarterTurns: edit.turns)
        refreshPage()
    }
    private func refreshPage() {
        tileButtons.forEach { $0.removeFromSuperview() }; tileButtons.removeAll()
        let width = tiles.bounds.width / CGFloat(columns)
        let height = tiles.bounds.height / CGFloat(rows)
        for cell in 0..<perPage {
            let index = page * perPage + cell
            let button = NSButton()
            button.frame = NSRect(x: CGFloat(cell % columns) * width + 2, y: tiles.bounds.height - CGFloat(cell / columns + 1) * height + 2, width: width - 4, height: height - 4)
            button.imageScaling = .scaleProportionallyUpOrDown
            button.imagePosition = .imageOnly
            button.bezelStyle = .regularSquare
            if index < rendered.count {
                button.image = rendered[index]; button.title = "\(index + 1)"
                button.tag = index; button.target = self; button.action = #selector(selectTile(_:))
                button.setAccessibilityLabel(String(format: NSLocalizedString("Print image %d", comment: ""), index + 1))
                button.state = index == selected ? .on : .off
            } else { button.title = NSLocalizedString("Empty", comment: ""); button.isEnabled = false }
            tiles.addSubview(button); tileButtons.append(button)
        }
        pageLabel.stringValue = String(format: NSLocalizedString("Page %d of %d · %d images", comment: ""), page + 1, pageCount, plain.count)
        if edits.indices.contains(selected) {
            selector.selectItem(at: selected); zoom.doubleValue = edits[selected].zoom
            annotation.state = edits[selected].annotations ? .on : .off
        }
    }

    static func filmAspectRatio(_ size: String, landscape: Bool) -> CGFloat {
        let normalized = size.uppercased().replacingOccurrences(of: "_", with: ".")
        let dimensions = normalized.components(separatedBy: CharacterSet(charactersIn: "0123456789.").inverted).compactMap(Double.init)
        let ratio: Double
        if normalized == "A4" || normalized == "A3" { ratio = 1 / sqrt(2) }
        else if dimensions.count == 2, dimensions[0] > 0, dimensions[1] > 0 { ratio = dimensions[0] / dimensions[1] }
        else { ratio = 14.0 / 17.0 }
        return CGFloat(landscape ? 1 / ratio : ratio)
    }

    /// Render offscreen at source pixel resolution; never mutate the source image.
    @objc public static func render(_ source: NSImage, zoom: Double, quarterTurns: Int) -> NSImage {
        let sourceBitmap = source.tiffRepresentation.flatMap { NSBitmapImageRep(data: $0) }
        guard let cgImage = sourceBitmap?.cgImage ?? source.cgImage(forProposedRect: nil, context: nil, hints: nil),
              let context = CGContext(data: nil, width: cgImage.width, height: cgImage.height, bitsPerComponent: 8, bytesPerRow: cgImage.width * 4, space: cgImage.colorSpace ?? CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return source }
        let width = CGFloat(cgImage.width), height = CGFloat(cgImage.height)
        let turns = ((quarterTurns % 4) + 4) % 4
        let factor = CGFloat(zoom.isFinite ? min(4, max(0.25, zoom)) : 1)
        context.setFillColor(gray: 0, alpha: 1)
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        context.translateBy(x: width / 2, y: height / 2)
        context.rotate(by: CGFloat(turns) * .pi / 2)
        let fit = turns % 2 == 0 ? CGFloat(1) : min(width / height, height / width)
        context.interpolationQuality = fit * factor == 1 ? .none : .high
        context.scaleBy(x: fit * factor, y: fit * factor)
        context.draw(cgImage, in: CGRect(x: -width / 2, y: -height / 2, width: width, height: height))
        guard let result = context.makeImage() else { return source }
        return NSImage(cgImage: result, size: NSSize(width: width, height: height))
    }
}
