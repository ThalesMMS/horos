#!/usr/bin/env python3
"""#384 A native RGB/pixel-aspect, real cancellation checkpoints and hidden PDF metadata."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
driver = r'''
import AppKit
import PDFKit

@main struct Check {
    static func main() {
        _ = NSApplication.shared
        let directory = PrintSelection.newSpoolDirectory()
        defer { precondition(PrintSelection.discardSpoolDirectory(directory)) }
        var rgb = [UInt8](repeating: 0, count: 64*96*4)
        for y in 0..<96 { for x in 0..<64 {
            let at = (y*64+x)*4
            rgb[at] = UInt8(x*4); rgb[at+1] = UInt8(y*2)
            rgb[at+2] = x % 2 == 0 ? 240 : 17; rgb[at+3] = 255
        }}
        let image = CGImage(width: 64, height: 96, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: 64*4,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                            provider: CGDataProvider(data: Data(rgb) as CFData)!, decode: nil, shouldInterpolate: false, intent: .defaultIntent)!
        let raster = PrintRaster()
        // Logical screen size is deliberately half resolution.
        raster.image = NSImage(cgImage: image, size: NSSize(width: 32, height: 48))
        raster.pixelRatio = 2
        let data = PrintSelection.pagePDF(from: raster, orientation: "asStored")!
        let document = PDFDocument(data: data)!
        let page = document.page(at: 0)!
        precondition(page.bounds(for: .mediaBox) == CGRect(x: 0, y: 0, width: 64, height: 192))
        var expected = [UInt8](repeating: 0, count: 64*192*4)
        var actual = expected
        func render(_ memory: UnsafeMutableRawBufferPointer, _ draw: (CGContext)->Void) {
            let context = CGContext(data: memory.baseAddress, width: 64, height: 192, bitsPerComponent: 8, bytesPerRow: 64*4,
                                    space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            context.interpolationQuality = .none
            draw(context)
        }
        expected.withUnsafeMutableBytes { memory in render(memory) { $0.draw(image, in: CGRect(x: 0, y: 0, width: 64, height: 192)) } }
        actual.withUnsafeMutableBytes { memory in render(memory) { $0.drawPDFPage(page.pageRef!) } }
        precondition(actual == expected, "full RGB pixels or non-square pixel geometry changed")
        raster.pixelRatio = .nan
        precondition(PrintSelection.pagePDF(from: raster, orientation: "asStored") == nil)
        raster.pixelRatio = 2

        let entry = PrintEntry(); entry.title = "fixture"
        let job = PrintJob(); job.entries = [entry, entry, entry]; job.success = true
        var loaded = 0, cancelled = false
        let stopped = PrintSelection.spool(job, directory: directory, rasterAt: { index in
            loaded += 1
            if index == 1 { cancelled = true; return nil }
            return raster
        }, continueAfter: { _, _ in !cancelled })
        precondition(stopped.cancelled && !stopped.success && stopped.pages.isEmpty && loaded == 2,
                     "cancellation during a loader is not an unreadable-file failure")
        precondition(try! FileManager.default.contentsOfDirectory(atPath: directory).isEmpty)
        var completed = [Int]()
        let ok = PrintSelection.spool(job, directory: directory, rasterAt: { _ in raster }, continueAfter: { count, total in
            precondition(total == 3)
            completed.append(count); return true
        })
        precondition(ok.success && ok.preparedCount == 3 && ok.pages.count == 3)
        precondition(completed == completed.sorted() && completed.first == 0 && completed.last == 3)
        precondition(PrintSelection.discardSpoolDirectory(directory))

        document.documentAttributes = [PDFDocumentAttribute.authorAttribute: "HIDDEN-PATIENT-384", PDFDocumentAttribute.titleAttribute: "HIDDEN-ID-384"]
        let hidden = PDFAnnotation(bounds: CGRect(x: 0, y: 0, width: 40, height: 20), forType: .freeText, withProperties: nil)
        hidden.contents = "HIDDEN-PATIENT-384"; hidden.shouldDisplay = false; hidden.shouldPrint = true
        page.addAnnotation(hidden)
        let visible = PDFAnnotation(bounds: CGRect(x: 0, y: 25, width: 40, height: 20), forType: .freeText, withProperties: nil)
        visible.contents = "VISIBLE-OVERLAY"; visible.userName = "HIDDEN-AUTHOR-384"
        visible.shouldDisplay = true; visible.shouldPrint = true; page.addAnnotation(visible)
        let report = PrintRaster(); report.pdfBytes = document.dataRepresentation()!
        job.entries = [entry]
        let filtered = PrintSelection.spool(job, directory: directory, cancelAfter: -1, rasters: [report])
        precondition(filtered.success)
        let output = PDFDocument(url: filtered.pages[0].url!)!
        precondition(output.documentAttributes?[PDFDocumentAttribute.authorAttribute] == nil && output.documentAttributes?[PDFDocumentAttribute.titleAttribute] == nil)
        precondition(output.page(at: 0)!.annotations.count == 1)
        precondition(output.page(at: 0)!.annotations[0].contents == "VISIBLE-OVERLAY")
        precondition(output.page(at: 0)!.annotations[0].userName == nil)
        precondition(page.annotations.count == 2 && visible.userName == "HIDDEN-AUTHOR-384", "scrubbing mutated the original")

        let info = NSPrintInfo()
        info.orientation = .landscape
        info.dictionary()[NSPrintInfo.AttributeKey.allPages] = false
        info.dictionary()[NSPrintInfo.AttributeKey.firstPage] = 99
        let operation = PrintSelection.printOperation(for: filtered, printInfo: info)!
        precondition(operation.showsPrintPanel && operation.showsProgressPanel)
        precondition(operation.jobTitle == "Horos")
        precondition(info.orientation == .landscape, "selected paper orientation changed")
        precondition((info.dictionary()[NSPrintInfo.AttributeKey.firstPage] as? NSNumber)?.intValue != 99, "stale print range survived")
        precondition(PrintSelection.printOperation(for: stopped, printInfo: info) == nil)
        print("PASS: 49152 RGB bytes equal at native resolution/pixel ratio, loader cancellation, monotonic progress, hidden metadata/annotations, print panel range and orientation")
    }
}
'''
with tempfile.TemporaryDirectory(prefix='horos-print-384-raster-') as temporary:
    folder = Path(temporary)
    (folder / 'Check.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(root / 'Horos/Sources/PrintSelection.swift'), str(folder / 'Check.swift'), '-o', str(folder / 'check')], check=True, timeout=60)
    subprocess.run([str(folder / 'check')], check=True, timeout=30)
