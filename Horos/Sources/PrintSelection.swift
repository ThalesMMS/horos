import Foundation

/// Database-window print selection for #384 package A.
///
/// File > Print on the browser must use the effective study/series/image
/// selection, not the outline view. OsiriX annotation archives inside a study
/// are not clinical reports. Whole-series multiframe objects expand to frames.
/// Cancel stops further pages; a partial job is not success. Temp files are
/// page indexes, not patient identifiers.
///
/// Package B (registered GIF / clipboard) depends on #378 and is not this type.
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
    @objc public static let gifBlockedOnRegistration = "Registered GIF export depends on longitudinal registration (#378) and is not part of print package A."

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
        uid == encapsulatedPDF || uid.hasPrefix("1.2.840.10008.5.1.4.1.1.104")
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
                entry.frame = expandFrames ? offset : baseFrame
                entry.frameCount = expandFrames ? item.numberOfFrames : 1
                entry.patientName = item.patientName
                entries.append(entry)
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
        _ = orientation
        if raster.missing { return nil }
        if let pdf = raster.pdfBytes, pdf.isEmpty == false { return pdf }
        guard raster.width > 0, raster.height > 0,
              raster.gray.count >= raster.width * raster.height else {
            return nil
        }
        return grayPDF(width: raster.width, height: raster.height, gray: raster.gray)
    }

    @objc public static func mediaBox(in data: Data) -> PrintMediaBox {
        let box = PrintMediaBox()
        guard let text = String(data: data, encoding: .isoLatin1) else { return box }
        guard let regex = try? NSRegularExpression(
            pattern: #"MediaBox\s*\[\s*0\s+0\s+(\d+)\s+(\d+)\s*\]"#) else { return box }
        let range = NSRange(text.startIndex..., in: text)
        guard let match = regex.firstMatch(in: text, range: range),
              match.numberOfRanges == 3,
              let w = Range(match.range(at: 1), in: text),
              let h = Range(match.range(at: 2), in: text) else { return box }
        box.width = Int(text[w]) ?? 0
        box.height = Int(text[h]) ?? 0
        return box
    }

    @objc public static func pageWasRotated(_ data: Data) -> Bool {
        let box = mediaBox(in: data)
        guard let text = String(data: data, encoding: .isoLatin1) else { return false }
        guard let regex = try? NSRegularExpression(
            pattern: #"\/Width\s+(\d+)\/Height\s+(\d+)"#) else { return false }
        let range = NSRange(text.startIndex..., in: text)
        guard let match = regex.firstMatch(in: text, range: range),
              match.numberOfRanges == 3,
              let w = Range(match.range(at: 1), in: text),
              let h = Range(match.range(at: 2), in: text),
              let imageWidth = Int(text[w]),
              let imageHeight = Int(text[h]) else { return false }
        return imageWidth == box.height && imageHeight == box.width && imageWidth != imageHeight
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
        let spool = PrintSpool()
        spool.openedViewer = false
        spool.usedDatabaseRaster = true
        if job.refusal.isEmpty == false {
            spool.refusal = job.refusal
            return spool
        }
        let dir = URL(fileURLWithPath: directory, isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for (index, entry) in job.entries.enumerated() {
            if cancelAfter >= 0 && index >= cancelAfter {
                spool.cancelled = true
                spool.refusal = cancelledRefusal
                spool.success = false
                return spool
            }
            let raster: PrintRaster
            if index < rasters.count {
                raster = rasters[index]
            } else {
                raster = PrintRaster()
                raster.missing = true
            }
            guard let data = pagePDF(from: raster, orientation: "asStored") else {
                spool.refusal = unreadableEntryRefusal(title: entry.title)
                spool.pages = []
                spool.success = false
                return spool
            }
            let name = pageTemporaryName(index: index, patientName: entry.patientName)
            let url = dir.appendingPathComponent(name)
            do {
                try data.write(to: url, options: .atomic)
            } catch {
                spool.refusal = unreadableEntryRefusal(title: entry.title)
                spool.pages = []
                spool.success = false
                return spool
            }
            let page = PrintPage()
            page.url = url
            let box = mediaBox(in: data)
            page.width = box.width
            page.height = box.height
            page.rotated = pageWasRotated(data)
            spool.pages.append(page)
        }
        spool.success = spool.pages.isEmpty == false
        return spool
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
    public var missing: Bool = false

    @objc public static func gray(width: Int, height: Int, value: Int) -> PrintRaster {
        let raster = PrintRaster()
        raster.width = width
        raster.height = height
        let clamped = UInt8(max(0, min(255, value)))
        raster.gray = Data(repeating: clamped, count: max(0, width * height))
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
    public var openedViewer: Bool = false
    public var usedDatabaseRaster: Bool = true
}

@objc(HorosPrintMediaBox)
@objcMembers public final class PrintMediaBox: NSObject {
    public var width: Int = 0
    public var height: Int = 0
}
