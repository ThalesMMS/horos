import Foundation
import AppKit
import PDFKit

/// Database-window print selection for #384 package A.
///
/// File > Print on the browser must use the effective study/series/image
/// selection, not the outline view. OsiriX annotation archives inside a study
/// are not clinical reports. Whole-series multiframe objects expand to frames.
/// Cancel stops further pages; a partial job is not success. Temp files are
/// page indexes, not patient identifiers.
///
/// Package B (registered GIF / clipboard) is `HorosRegisteredGIF`, not this type.
/// DICOM film print, Pages/Word and report editors stay on their own issues.
@objc(HorosPrintRecord)
@objcMembers public final class PrintRecord: NSObject {
    public var kind: String = "series"
    public var seriesSOPClassUID: String = ""
    public var modality: String = ""
    public var seriesName: String = ""
    public var path: String = ""
    public var title: String = ""
    public var imageCount: Int = 1
    public var numberOfFrames: Int = 1
    public var frameID: Int = 0
    public var parentIsStudy: Bool = false
    public var patientName: String = ""
    public var patientID: String = ""
    public var requestedOrientation: String = "asStored"
    public var windowWidth: Double = 0
    public var windowLevel: Double = 0

    public convenience init(kind: String, seriesSOPClassUID: String, modality: String,
                            seriesName: String, path: String, imageCount: Int,
                            numberOfFrames: Int, parentIsStudy: Bool) {
        self.init()
        self.kind = kind
        self.seriesSOPClassUID = seriesSOPClassUID
        self.modality = modality
        self.seriesName = seriesName
        self.path = path
        self.title = seriesName
        self.imageCount = imageCount
        self.numberOfFrames = numberOfFrames
        self.parentIsStudy = parentIsStudy
    }
}

@objc(HorosPrintEntry)
@objcMembers public final class PrintEntry: NSObject {
    public var path: String = ""
    public var title: String = ""
    public var isReport: Bool = false
    public var frame: Int = 0
    public var frameCount: Int = 1
    public var sopClassUID: String = ""
    /// -1 means the entire report; a selected database PDF/SR frame is one page.
    public var reportPage: Int = -1
    public var windowWidth: Double = 0
    public var windowLevel: Double = 0
    public var patientName: String = ""
}

@objc(HorosPrintJob)
@objcMembers public final class PrintJob: NSObject {
    public var entries: [PrintEntry] = []
    public var refusal: String = ""
    public var cancelled: Bool = false
    public var usedEffectiveSelection: Bool = true
    public var printedDatabaseTable: Bool = false
    public var success: Bool = false
    public var preparedCount: Int = 0
}

@objc(HorosPrintSelection)
public final class PrintSelection: NSObject {
    @objc public static let emptySelectionRefusal = "No printable images or reports are selected."
    @objc public static let cancelledRefusal = "The print job was cancelled."
    @objc public static let prepareFailureRefusal = "The selection could not be prepared for printing."
    @objc public static let gifBlockedOnRegistration = "Registered GIF export is HorosRegisteredGIF (#384 package B, on the registration of #378); it is not part of print package A."

    @objc public static let encapsulatedPDF = "1.2.840.10008.5.1.4.1.1.104.1"
    @objc public static let basicTextSR = "1.2.840.10008.5.1.4.1.1.88.11"
    @objc public static let ctImageStorage = "1.2.840.10008.5.1.4.1.1.2"

    @objc public static func mayPrintOutlineView() -> Bool { false }
    @objc public static func replacesReportEditors() -> Bool { false }
    @objc public static func replacesDICOMFilmPrint() -> Bool { false }
    @objc public static func implementsRegisteredGIF() -> Bool { false }
    @objc public static func autoRotatesPages() -> Bool { false }

    @objc public static func isStructuredReport(_ uid: String) -> Bool {
        uid.hasPrefix("1.2.840.10008.5.1.4.1.1.88")
    }

    @objc public static func isEncapsulatedPDF(_ uid: String) -> Bool {
        uid == encapsulatedPDF
    }

    @objc public static func isReport(sopClassUID: String, modality: String) -> Bool {
        isStructuredReport(sopClassUID) || isEncapsulatedPDF(sopClassUID) ||
            modality.lowercased() == "pdf" || modality.uppercased() == "SR"
    }

    @objc public static func isAnnotationArchive(_ name: String) -> Bool {
        name.hasPrefix("OsiriX ")
    }

    @objc public static func isPrintableSeries(sopClassUID: String, modality: String, name: String,
                                                parentIsStudy: Bool) -> Bool {
        if parentIsStudy && isAnnotationArchive(name) { return false }
        if isReport(sopClassUID: sopClassUID, modality: modality) { return true }
        if sopClassUID.isEmpty { return false }
        if isStructuredReport(sopClassUID) { return true }
        if sopClassUID.hasPrefix("1.2.840.10008.5.1.4.1.1.66") { return false }
        if sopClassUID.hasPrefix("1.2.840.10008.5.1.4.1.1.11") { return false }
        if sopClassUID.hasPrefix("1.2.840.10008.5.1.4.1.1.481") { return false }
        return true
    }

    @objc public static func pageTemporaryName(index: Int, patientName: String) -> String {
        _ = patientName
        return String(format: "page-%04d.pdf", index)
    }

    /// The legacy viewer spools rendered frames, not PDF pages, and names them
    /// by frame index alone.
    @objc(viewerPageTemporaryNameWithIndex:)
    public static func viewerPageTemporaryName(index: Int) -> String {
        String(format: "frame-%05d.tif", index)
    }

    @objc public static func temporaryNameLeaksIdentifiers(_ name: String, patientName: String, patientID: String) -> Bool {
        if patientName.isEmpty == false && name.localizedCaseInsensitiveContains(patientName) { return true }
        if patientID.isEmpty == false && name.contains(patientID) { return true }
        return false
    }

    // Pin the Objective-C name: without it Swift folds the `from` label into the
    // base name and exports jobFrom:source:, which is not what the caller says.
    @objc(jobFromItems:source:)
    public static func job(from items: [PrintRecord], source: String) -> PrintJob {
        let job = PrintJob()
        job.usedEffectiveSelection = source != "databaseTable"
        job.printedDatabaseTable = source == "databaseTable"
        if source == "databaseTable" {
            job.refusal = "File > Print must use the effective selection, not the database table."
            job.success = false
            return job
        }
        var entries: [PrintEntry] = []
        var seen = Set<String>()
        for item in items {
            guard isPrintableSeries(sopClassUID: item.seriesSOPClassUID, modality: item.modality,
                                    name: item.seriesName, parentIsStudy: item.parentIsStudy) else {
                continue
            }
            let report = isReport(sopClassUID: item.seriesSOPClassUID, modality: item.modality)
            let expandFrames = !report && item.kind != "image" && item.imageCount == 1 && item.numberOfFrames > 1
            let frames = expandFrames ? item.numberOfFrames : 1
            let baseFrame = item.kind == "image" ? item.frameID : 0
            for offset in 0..<frames {
                let entry = PrintEntry()
                entry.path = item.path
                entry.title = item.title.isEmpty ? item.seriesName : item.title
                entry.isReport = report
                entry.reportPage = report && item.kind == "image" && item.numberOfFrames > 1 ? item.frameID : -1
                entry.frame = report ? entry.reportPage : (expandFrames ? offset : baseFrame)
                entry.frameCount = expandFrames ? item.numberOfFrames : 1
                entry.patientName = item.patientName
                entry.sopClassUID = item.seriesSOPClassUID
                entry.windowWidth = item.windowWidth
                entry.windowLevel = item.windowLevel
                // An image may be selected both directly and through its series.
                // Deduplicate the actual frame, retaining the first selected order.
                let identity = "\(entry.path.utf8.count):\(entry.path):\(entry.frame)"
                if seen.insert(identity).inserted { entries.append(entry) }
            }
        }
        if entries.isEmpty {
            job.refusal = emptySelectionRefusal
            job.success = false
            return job
        }
        job.entries = entries
        job.success = true
        job.preparedCount = entries.count
        return job
    }

    @objc public static func prepare(_ job: PrintJob, cancelAfter: Int) -> PrintJob {
        if job.refusal.isEmpty == false { return job }
        let prepared = PrintJob()
        prepared.usedEffectiveSelection = job.usedEffectiveSelection
        prepared.printedDatabaseTable = false
        if cancelAfter >= 0 && cancelAfter < job.entries.count {
            prepared.entries = Array(job.entries.prefix(cancelAfter))
            prepared.cancelled = true
            prepared.refusal = cancelledRefusal
            prepared.preparedCount = cancelAfter
            prepared.success = false
            return prepared
        }
        prepared.entries = job.entries
        prepared.preparedCount = job.entries.count
        prepared.success = true
        return prepared
    }

    @objc public static func unreadableEntryRefusal(title: String) -> String {
        "\"\(title)\" could not be read or does not permit printing. Nothing was printed."
    }

    @objc public static func requiresViewerToSpool() -> Bool { false }

    @objc public static func pagePDF(from raster: PrintRaster, orientation: String) -> Data? {
        // Paper orientation belongs to NSPrintInfo. Never rotate source pixels to
        // guess what the user will select in the print panel.
        guard !raster.missing, orientation == "asStored" else { return nil }
        if let pdf = raster.pdfBytes {
            guard let document = PDFDocument(data: pdf), document.pageCount > 0,
                  !document.isLocked, document.allowsPrinting else { return nil }
            return pdf
        }
        if let image = raster.image {
            var proposed = CGRect(origin: .zero, size: image.size)
            guard let cgImage = image.cgImage(forProposedRect: &proposed, context: nil, hints: nil),
                  raster.pixelRatio.isFinite, raster.pixelRatio > 0 else { return nil }
            let data = NSMutableData()
            var box = CGRect(x: 0, y: 0, width: Double(cgImage.width),
                             height: Double(cgImage.height) * raster.pixelRatio)
            guard box.width.isFinite, box.height.isFinite,
                  let consumer = CGDataConsumer(data: data),
                  let context = CGContext(consumer: consumer, mediaBox: &box, nil) else { return nil }
            context.beginPDFPage(nil)
            context.interpolationQuality = .none
            context.draw(cgImage, in: box)
            context.endPDFPage()
            context.closePDF()
            return data as Data
        }
        let (count, overflow) = raster.width.multipliedReportingOverflow(by: raster.height)
        guard !overflow, raster.width > 0, raster.height > 0, raster.gray.count >= count else { return nil }
        return grayPDF(width: raster.width, height: raster.height, gray: raster.gray)
    }

    @objc public static func mediaBox(in data: Data) -> PrintMediaBox {
        let box = PrintMediaBox()
        if let page = PDFDocument(data: data)?.page(at: 0) {
            let bounds = page.bounds(for: .mediaBox)
            box.width = Int(bounds.width.rounded())
            box.height = Int(bounds.height.rounded())
        }
        return box
    }

    @objc public static func pageWasRotated(_ data: Data) -> Bool {
        guard let page = PDFDocument(data: data)?.page(at: 0) else { return false }
        return page.rotation % 360 != 0
    }

    /// Where a print job's pages are spooled: a directory of its own under the
    /// temporary directory (#384).
    ///
    /// The pages carry patient names, dates and images. Whoever asks for one has
    /// to be able to take it away again, which is what `discardSpool` is for.
    @objc public static let spoolDirectoryPrefix = "horos-print-"

    @objc(newSpoolDirectory)
    public static func newSpoolDirectory() -> String {
        (NSTemporaryDirectory() as NSString)
            .appendingPathComponent(spoolDirectoryPrefix + UUID().uuidString)
    }

    /// Remove a spool directory and everything in it.
    ///
    /// The pages rendered for printing are identifiable: a patient name and a
    /// picture, on disk, in a place nothing cleans. #384 says that hidden
    /// identifiers must not survive in pages or temporaries, and until this
    /// existed every print left a directory of them behind for good.
    ///
    /// It refuses any path that is not one of ours under the temporary
    /// directory, so a wrong argument removes nothing rather than something
    /// else.
    @objc(discardSpoolDirectory:)
    @discardableResult
    public static func discardSpoolDirectory(_ directory: String) -> Bool {
        guard isSpoolDirectory(directory) else { return false }
        do {
            try FileManager.default.removeItem(atPath: directory)
            return true
        } catch {
            return !FileManager.default.fileExists(atPath: directory)
        }
    }

    /// Whether a path is a spool directory this class would have made.
    @objc(isSpoolDirectory:)
    public static func isSpoolDirectory(_ directory: String) -> Bool {
        let path = (directory as NSString).standardizingPath
        let temporary = (NSTemporaryDirectory() as NSString).standardizingPath
        let name = (path as NSString).lastPathComponent
        guard name.hasPrefix(spoolDirectoryPrefix), name.count > spoolDirectoryPrefix.count
        else { return false }
        let parent = (path as NSString).deletingLastPathComponent
        return parent == temporary || parent + "/" == temporary || parent == temporary + "/"
            || (temporary as NSString).standardizingPath == (parent as NSString).standardizingPath
    }

    @objc(spool:directory:cancelAfter:rasters:)
    public static func spool(_ job: PrintJob, directory: String, cancelAfter: Int,
                             rasters: [PrintRaster]) -> PrintSpool {
        spool(job, directory: directory, rasterAt: { index in
            index < rasters.count ? rasters[index] : nil
        }, continueAfter: { completed, total in cancelAfter < 0 || cancelAfter >= total || completed < cancelAfter })
    }

    /// One entry at a time keeps a long selection from retaining every decoded
    /// image. Check cancellation before decoding, after decoding and before
    /// writing each report page. No failed or cancelled spool is printable.
    @objc(spool:directory:rasterAt:continueAfter:)
    public static func spool(_ job: PrintJob, directory: String,
                             rasterAt: (Int) -> PrintRaster?,
                             continueAfter: (Int, Int) -> Bool) -> PrintSpool {
        let spool = PrintSpool()
        guard job.refusal.isEmpty, !job.entries.isEmpty else {
            spool.refusal = job.refusal.isEmpty ? emptySelectionRefusal : job.refusal
            return spool
        }
        let dir = URL(fileURLWithPath: directory, isDirectory: true)
        var written: [URL] = []
        var reportPages = Set<String>()
        defer {
            if !spool.success {
                for url in written { try? FileManager.default.removeItem(at: url) }
                spool.pages = []
            }
        }
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true,
                                                     attributes: [.posixPermissions: 0o700])
        } catch {
            spool.refusal = prepareFailureRefusal
            return spool
        }
        func proceed(_ completed: Int) -> Bool {
            if continueAfter(completed, job.entries.count) { return true }
            spool.cancelled = true
            spool.refusal = cancelledRefusal
            return false
        }
        for (index, entry) in job.entries.enumerated() {
            guard proceed(index) else { return spool }
            let completed = autoreleasepool { () -> Bool in
                let raster = rasterAt(index)
                guard proceed(index) else { return false }
                guard let raster = raster,
                      let data = pagePDF(from: raster, orientation: "asStored"),
                      let document = PDFDocument(data: data), document.allowsPrinting,
                      !document.isLocked, document.pageCount > 0 else {
                    spool.refusal = unreadableEntryRefusal(title: entry.title)
                    return false
                }
                guard proceed(index) else { return false }
                guard entry.reportPage < document.pageCount else {
                    spool.refusal = unreadableEntryRefusal(title: entry.title)
                    return false
                }
                let pageIndices = entry.isReport && entry.reportPage >= 0 ? [entry.reportPage] : Array(0..<document.pageCount)
                for pageIndex in pageIndices {
                    guard proceed(index) else { return false }
                    // A page selected directly and again through the whole
                    // report is printed once, in its first selected position.
                    if entry.isReport {
                        let identity = "\(entry.path.utf8.count):\(entry.path):\(pageIndex)"
                        if !reportPages.insert(identity).inserted { continue }
                    }
                    guard let source = document.page(at: pageIndex),
                          let copy = source.copy() as? PDFPage else { return false }
                    // A hidden annotation must not reappear just because its
                    // separate PDF print flag was left on. Visible annotations
                    // keep their appearance; their author is not printed content.
                    for annotation in copy.annotations {
                        if !annotation.shouldDisplay || !annotation.shouldPrint {
                            copy.removeAnnotation(annotation)
                        } else {
                            annotation.userName = nil
                        }
                    }
                    let onePage = PDFDocument()
                    onePage.insert(copy, at: 0)
                    // Source metadata is not a print overlay. Do not propagate
                    // hidden author/patient identifiers into the PDF info dict.
                    onePage.documentAttributes = [:]
                    let url = dir.appendingPathComponent(pageTemporaryName(index: written.count, patientName: ""))
                    guard let bytes = onePage.dataRepresentation() else {
                        spool.refusal = unreadableEntryRefusal(title: entry.title)
                        return false
                    }
                    do {
                        // A fresh job owns fresh names, never overwrite an input.
                        try bytes.write(to: url, options: .withoutOverwriting)
                        written.append(url)
                        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
                    } catch {
                        spool.refusal = prepareFailureRefusal
                        return false
                    }
                    let page = PrintPage()
                    page.url = url
                    let bounds = source.bounds(for: .mediaBox)
                    page.width = Int(bounds.width.rounded())
                    page.height = Int(bounds.height.rounded())
                    page.rotated = source.rotation % 360 != 0
                    spool.pages.append(page)
                }
                spool.preparedCount = index + 1
                return true
            }
            guard completed else { return spool }
        }
        guard proceed(job.entries.count) else { return spool }
        spool.success = !spool.pages.isEmpty
        return spool
    }

    @objc(printOperationForSpool:printInfo:)
    public static func printOperation(for spool: PrintSpool, printInfo: NSPrintInfo) -> NSPrintOperation? {
        guard spool.success, !spool.cancelled, spool.refusal.isEmpty, !spool.pages.isEmpty else { return nil }
        let document = PDFDocument()
        for item in spool.pages {
            guard let url = item.url, let part = PDFDocument(url: url), part.pageCount == 1,
                  part.allowsPrinting, !part.isLocked, let page = part.page(at: 0)?.copy() as? PDFPage else { return nil }
            document.insert(page, at: document.pageCount)
        }
        document.documentAttributes = [:]
        // Start from the complete prepared job, not a previous job's range.
        // The user can still choose a partial range in this operation's panel.
        printInfo.dictionary()[NSPrintInfo.AttributeKey.allPages] = true
        printInfo.dictionary()[NSPrintInfo.AttributeKey.selectionOnly] = false
        printInfo.dictionary().removeObject(forKey: NSPrintInfo.AttributeKey.firstPage)
        printInfo.dictionary().removeObject(forKey: NSPrintInfo.AttributeKey.lastPage)
        let operation = document.printOperation(for: printInfo, scalingMode: .pageScaleDownToFit, autoRotate: false)
        operation?.showsPrintPanel = true
        operation?.showsProgressPanel = true
        // Avoid names from reports in the printer queue and saved-file proposal.
        operation?.jobTitle = "Horos"
        return operation
    }

    private static func grayPDF(width: Int, height: Int, gray: Data) -> Data {
        let image = Data(gray.prefix(width * height))
        let content = "\(width) 0 0 \(height) 0 0 cm /Im0 Do\n"
        let contentBytes = Data(content.utf8)
        var objects: [Data] = []
        objects.append(pdfObject(1, "<< /Type /Catalog /Pages 2 0 R >>\n"))
        objects.append(pdfObject(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n"))
        objects.append(pdfObject(
            3,
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 \(width) \(height)] /Contents 4 0 R /Resources << /XObject << /Im0 5 0 R >> >> >>\n"))
        var contents = Data("4 0 obj\n<< /Length \(contentBytes.count) >>\nstream\n".utf8)
        contents.append(contentBytes)
        contents.append(Data("endstream\nendobj\n".utf8))
        objects.append(contents)
        var imageObj = Data("5 0 obj\n<< /Type /XObject /Subtype /Image /Width \(width) /Height \(height) /ColorSpace /DeviceGray /BitsPerComponent 8 /Length \(image.count) >>\nstream\n".utf8)
        imageObj.append(image)
        imageObj.append(Data("\nendstream\nendobj\n".utf8))
        objects.append(imageObj)

        var body = Data("%PDF-1.4\n".utf8)
        var offsets: [Int] = [0]
        for object in objects {
            offsets.append(body.count)
            body.append(object)
        }
        let xrefAt = body.count
        var xref = "xref\n0 \(objects.count + 1)\n0000000000 65535 f \n"
        for offset in offsets.dropFirst() {
            xref += String(format: "%010d 00000 n \n", offset)
        }
        xref += "trailer\n<< /Size \(objects.count + 1) /Root 1 0 R >>\nstartxref\n\(xrefAt)\n%%EOF\n"
        body.append(Data(xref.utf8))
        return body
    }

    private static func pdfObject(_ number: Int, _ body: String) -> Data {
        Data("\(number) 0 obj\n\(body)endobj\n".utf8)
    }
}

@objc(HorosPrintRaster)
@objcMembers public final class PrintRaster: NSObject {
    public var width: Int = 0
    public var height: Int = 0
    public var gray: Data = Data()
    public var pdfBytes: Data?
    public var image: NSImage?
    public var pixelRatio: Double = 1
    public var missing: Bool = false

    @objc public static func gray(width: Int, height: Int, value: Int) -> PrintRaster {
        let raster = PrintRaster()
        raster.width = width
        raster.height = height
        let clamped = UInt8(max(0, min(255, value)))
        let (count, overflow) = width.multipliedReportingOverflow(by: height)
        guard !overflow, width > 0, height > 0 else { raster.missing = true; return raster }
        raster.gray = Data(repeating: clamped, count: count)
        return raster
    }
}

@objc(HorosPrintPage)
@objcMembers public final class PrintPage: NSObject {
    public var url: URL?
    public var width: Int = 0
    public var height: Int = 0
    public var rotated: Bool = false
}

@objc(HorosPrintSpool)
@objcMembers public final class PrintSpool: NSObject {
    public var pages: [PrintPage] = []
    public var refusal: String = ""
    public var cancelled: Bool = false
    public var success: Bool = false
    public var preparedCount: Int = 0
    public var openedViewer: Bool = false
    public var usedDatabaseRaster: Bool = true
}

@objc(HorosPrintMediaBox)
@objcMembers public final class PrintMediaBox: NSObject {
    public var width: Int = 0
    public var height: Int = 0
}
