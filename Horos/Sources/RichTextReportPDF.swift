import AppKit

/// RTF and RTFD reports as PDF, drawn by the app itself (#649).
///
/// The conversion used to run /System/Library/Printers/Libraries/convert, gone since OS X 10.8, or
/// else cupsfilter, which on macOS 27 has no filter from text/rtf to application/pdf: it exited 1
/// and left the PDF the app had created empty, and every caller went on with it - the PDF export,
/// the DICOM PDF, the web portal, a burnt medium.
///
/// The report is read with NSAttributedString and laid out by TextKit in pages of the document's
/// own paper size and margins (the RTF defaults when it has none), then drawn as text into a PDF
/// context. The PDF replaces the destination only once it is complete and readable.
@objc(HorosRichTextReportPDF)
public final class RichTextReportPDF: NSObject {
    /// RTF's defaults: US Letter, 1.25 in left and right, 1 in top and bottom.
    private static let defaultPaper = NSSize(width: 612, height: 792)
    private static let defaultMargins = (left: CGFloat(90), right: CGFloat(90), top: CGFloat(72), bottom: CGFloat(72))
    private static let pageLimit = 5000

    @objc(convertReportAtPath:toPDFAtPath:error:)
    public static func convert(reportPath: String, toPDFAtPath pdfPath: String) throws {
        let source = URL(fileURLWithPath: reportPath)
        let package = source.pathExtension.lowercased() == "rtfd"
        var attributes: NSDictionary?
        let text: NSAttributedString
        do {
            text = try NSAttributedString(url: source,
                                          options: [.documentType: package ? NSAttributedString.DocumentType.rtfd : .rtf],
                                          documentAttributes: &attributes)
        } catch {
            throw failure(String(format: NSLocalizedString("The report could not be read as %@: %@", comment: ""),
                                 package ? "RTFD" : "RTF", error.localizedDescription))
        }

        var paper = (attributes?[NSAttributedString.DocumentAttributeKey.paperSize] as? NSValue)?.sizeValue ?? defaultPaper
        var margins = defaultMargins
        if let value = attributes?[NSAttributedString.DocumentAttributeKey.leftMargin] as? NSNumber { margins.left = CGFloat(value.doubleValue) }
        if let value = attributes?[NSAttributedString.DocumentAttributeKey.rightMargin] as? NSNumber { margins.right = CGFloat(value.doubleValue) }
        if let value = attributes?[NSAttributedString.DocumentAttributeKey.topMargin] as? NSNumber { margins.top = CGFloat(value.doubleValue) }
        if let value = attributes?[NSAttributedString.DocumentAttributeKey.bottomMargin] as? NSNumber { margins.bottom = CGFloat(value.doubleValue) }
        var area = NSSize(width: paper.width - margins.left - margins.right, height: paper.height - margins.top - margins.bottom)
        if paper.width < 72 || paper.height < 72 || area.width < 36 || area.height < 36 {
            paper = defaultPaper
            margins = defaultMargins
            area = NSSize(width: paper.width - margins.left - margins.right, height: paper.height - margins.top - margins.bottom)
        }

        // One text container a page, until every glyph has one.
        let storage = NSTextStorage(attributedString: text)
        let layout = NSLayoutManager()
        storage.addLayoutManager(layout)
        var pages: [NSRange] = []
        repeat {
            let container = NSTextContainer(size: area)
            layout.addTextContainer(container)
            let range = layout.glyphRange(for: container)
            if range.length == 0 && NSMaxRange(range) < layout.numberOfGlyphs || pages.count >= pageLimit {
                throw failure(NSLocalizedString("The report could not be laid out in pages: part of it does not fit a page.", comment: ""))
            }
            pages.append(range)
        } while NSMaxRange(pages[pages.count - 1]) < layout.numberOfGlyphs

        let destination = URL(fileURLWithPath: pdfPath)
        let temporary = destination.deletingLastPathComponent().appendingPathComponent(".horos-report-\(UUID().uuidString).pdf")
        defer { try? FileManager.default.removeItem(at: temporary) }
        var box = CGRect(origin: .zero, size: paper)
        guard let context = CGContext(temporary as CFURL, mediaBox: &box, [kCGPDFContextCreator: "Horos"] as CFDictionary) else {
            throw failure(String(format: NSLocalizedString("The PDF could not be created at %@.", comment: ""), pdfPath))
        }
        let previous = NSGraphicsContext.current
        for range in pages {
            context.beginPDFPage(nil)
            context.saveGState()
            // TextKit draws top-down: a flipped page, and a context that says so.
            context.translateBy(x: 0, y: paper.height)
            context.scaleBy(x: 1, y: -1)
            NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: true)
            let origin = NSPoint(x: margins.left, y: margins.top)
            layout.drawBackground(forGlyphRange: range, at: origin)
            layout.drawGlyphs(forGlyphRange: range, at: origin)
            NSGraphicsContext.current = previous
            context.restoreGState()
            context.endPDFPage()
        }
        context.closePDF()

        guard let written = CGPDFDocument(temporary as CFURL), written.numberOfPages == pages.count else {
            throw failure(String(format: NSLocalizedString("The PDF written for the report is not readable: %@", comment: ""), reportPath))
        }
        do {
            if FileManager.default.fileExists(atPath: pdfPath) {
                _ = try FileManager.default.replaceItemAt(destination, withItemAt: temporary)
            } else {
                try FileManager.default.moveItem(at: temporary, to: destination)
            }
        } catch {
            throw failure(String(format: NSLocalizedString("The PDF could not be saved at %@: %@", comment: ""), pdfPath, error.localizedDescription))
        }
    }

    private static func failure(_ description: String) -> NSError {
        NSError(domain: "HorosReportPDF", code: 1, userInfo: [NSLocalizedDescriptionKey: description])
    }
}
