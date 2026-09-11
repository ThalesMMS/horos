#!/usr/bin/env python3
"""#384 A compares real PDF pages/pixels, and refuses partial/corrupt print jobs."""
import argparse
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=root / 'Horos/Sources/PrintSelection.swift')
args = parser.parse_args()

driver = r'''
import Foundation
import AppKit
import PDFKit

func fixture() -> Data {
    let bytes = NSMutableData()
    var box = CGRect(x: 0, y: 0, width: 64, height: 96)
    let context = CGContext(consumer: CGDataConsumer(data: bytes)!, mediaBox: &box, nil)!
    for index in 0..<3 {
        context.beginPDFPage(nil)
        context.setFillColor(CGColor(red: index == 0 ? 1 : 0, green: index == 1 ? 1 : 0,
                                     blue: index == 2 ? 1 : 0, alpha: 1))
        context.fill(box)
        context.setFillColor(CGColor(gray: 0, alpha: 1))
        // Asymmetric one-pixel stripes detect rotation, reordering and loss of resolution.
        for x in stride(from: 1, to: 25, by: 2) { context.fill(CGRect(x: x, y: 3, width: 1, height: 19)) }
        context.endPDFPage()
    }
    context.closePDF()
    return bytes as Data
}
func pixels(_ page: PDFPage) -> [UInt8] {
    let box = page.bounds(for: .mediaBox)
    let width = Int(box.width), height = Int(box.height)
    var bytes = [UInt8](repeating: 0, count: width * height * 4)
    bytes.withUnsafeMutableBytes { memory in
        let context = CGContext(data: memory.baseAddress, width: width, height: height, bitsPerComponent: 8,
                                bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.interpolationQuality = .none
        context.setShouldAntialias(false)
        context.drawPDFPage(page.pageRef!)
    }
    return bytes
}
@main struct Check {
    static func main() {
        let manager = FileManager.default
        let sourceData = fixture()
        let source = PDFDocument(data: sourceData)!
        let directory = PrintSelection.newSpoolDirectory()
        defer { precondition(PrintSelection.discardSpoolDirectory(directory)) }
        let record = PrintEntry(); record.isReport = true; record.title = "synthetic report"
        let job = PrintJob(); job.entries = [record]; job.success = true
        let raster = PrintRaster(); raster.pdfBytes = sourceData
        let spool = PrintSelection.spool(job, directory: directory, cancelAfter: -1, rasters: [raster])
        precondition(spool.success && spool.pages.count == 3, "all report pages must be printed, not only the first")
        for index in 0..<3 {
            let output = PDFDocument(url: spool.pages[index].url!)!
            precondition(output.pageCount == 1)
            precondition(output.page(at: 0)!.bounds(for: .mediaBox) == CGRect(x: 0, y: 0, width: 64, height: 96))
            precondition(pixels(output.page(at: 0)!) == pixels(source.page(at: index)!), "pixels, color, orientation or page order changed")
            precondition(!spool.pages[index].rotated)
        }
        precondition(source.dataRepresentation() != nil && raster.pdfBytes == sourceData, "source must be preserved")
        precondition(PrintSelection.discardSpoolDirectory(directory))

        let invalid = PrintRaster(); invalid.pdfBytes = Data("%PDF-1.4 invalid".utf8)
        precondition(PrintSelection.pagePDF(from: invalid, orientation: "asStored") == nil, "PDF signature alone does not make a printable report")
        job.entries = [record, record]
        let failed = PrintSelection.spool(job, directory: directory, cancelAfter: -1, rasters: [raster, invalid])
        precondition(!failed.success && !failed.refusal.isEmpty && failed.pages.isEmpty)
        precondition(try! manager.contentsOfDirectory(atPath: directory).isEmpty, "failure left printable pages behind")
        for count in [0, 1] {
            let cancelled = PrintSelection.spool(job, directory: directory, cancelAfter: count, rasters: [raster, raster])
            precondition(cancelled.cancelled && !cancelled.success && cancelled.pages.isEmpty)
            precondition(try! manager.contentsOfDirectory(atPath: directory).isEmpty, "cancel left a partial report")
        }
        // Refuse to overwrite a source even if a caller accidentally chooses its directory.
        let collision = URL(fileURLWithPath: directory).appendingPathComponent("page-0000.pdf")
        try! sourceData.write(to: collision)
        let blocked = PrintSelection.spool(job, directory: directory, cancelAfter: -1, rasters: [raster, raster])
        precondition(!blocked.success && blocked.pages.isEmpty)
        precondition(try! Data(contentsOf: collision) == sourceData)
        precondition(PrintSelection.discardSpoolDirectory(directory))
        func reportRecord(_ frame: Int, _ kind: String) -> PrintRecord {
            let item = PrintRecord(kind: kind, seriesSOPClassUID: PrintSelection.encapsulatedPDF, modality: "DOC",
                                   seriesName: "report", path: "/synthetic/report.dcm", imageCount: 3,
                                   numberOfFrames: 3, parentIsStudy: false)
            item.frameID = frame; return item
        }
        let partial = PrintSelection.job(from: [reportRecord(2, "image"), reportRecord(0, "image")], source: "effective")
        let partialSpool = PrintSelection.spool(partial, directory: directory, cancelAfter: -1, rasters: [raster, raster])
        precondition(partialSpool.success && partialSpool.pages.count == 2)
        for (outputIndex, sourceIndex) in [2, 0].enumerated() {
            precondition(pixels(PDFDocument(url: partialSpool.pages[outputIndex].url!)!.page(at: 0)!) == pixels(source.page(at: sourceIndex)!))
        }
        precondition(PrintSelection.discardSpoolDirectory(directory))
        let rows = (0..<3).map { reportRecord($0, "series") }
        let indexed = PrintSelection.job(from: rows, source: "effective")
        precondition(indexed.entries.count == 1, "whole report with three database frames must be one document")
        let indexedSpool = PrintSelection.spool(indexed, directory: directory, cancelAfter: -1, rasters: [raster])
        precondition(indexedSpool.success && indexedSpool.pages.count == 3, "indexed PDF became nine pages")
        precondition(PrintSelection.discardSpoolDirectory(directory))
        let overlap = PrintSelection.job(from: [reportRecord(1, "image")] + rows, source: "effective")
        let overlapSpool = PrintSelection.spool(overlap, directory: directory, cancelAfter: -1, rasters: [raster, raster])
        precondition(overlapSpool.success && overlapSpool.pages.count == 3)
        for (outputIndex, sourceIndex) in [1, 0, 2].enumerated() {
            precondition(pixels(PDFDocument(url: overlapSpool.pages[outputIndex].url!)!.page(at: 0)!) == pixels(source.page(at: sourceIndex)!))
        }
        print("PASS: indexed/partial/overlapping report selection, 3 PDF pages, 73728 RGBA bytes equal to independent fixture; order/color/aspect/resolution; invalid PDF, cancellation and source preservation")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-print-384-pages-') as temporary:
    folder = Path(temporary)
    (folder / 'Check.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(args.source), str(folder / 'Check.swift'), '-o', str(folder / 'check')], check=True, timeout=60)
    subprocess.run([str(folder / 'check')], check=True, timeout=30)
