#!/usr/bin/env python3
"""Database print spools raster/PDF pages without opening a viewer (#384 A)."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/PrintSelection.swift'
assert source.is_file(), 'FAIL: PrintSelection.swift is missing'

driver = r'''
import Foundation

@main struct Check {
    static func main() {
        precondition(!PrintSelection.requiresViewerToSpool())
        precondition(!PrintSelection.autoRotatesPages())
        precondition(!PrintSelection.implementsRegisteredGIF())

        let tall = PrintRaster.gray(width: 10, height: 20, value: 128)
        let pdf = PrintSelection.pagePDF(from: tall, orientation: "asStored")
        precondition(pdf != nil, "as-stored raster must become a PDF page")
        let box = PrintSelection.mediaBox(in: pdf!)
        precondition(box.width == 10 && box.height == 20, "as-stored keeps 10x20, does not rotate to 20x10")
        precondition(!PrintSelection.pageWasRotated(pdf!))

        var report = PrintRaster()
        report.pdfBytes = Data("%PDF-1.4 report".utf8)
        let wrapped = PrintSelection.pagePDF(from: report, orientation: "asStored")
        precondition(wrapped == report.pdfBytes)

        let missing = PrintRaster()
        missing.missing = true
        precondition(PrintSelection.pagePDF(from: missing, orientation: "asStored") == nil)

        let job = PrintJob()
        let one = PrintEntry()
        one.path = "/tmp/ct.dcm"
        one.title = "Axial"
        one.patientName = "DOE^JOHN"
        job.entries = [one]
        job.success = true

        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("horos-print-spool-check", isDirectory: true)
        try? FileManager.default.removeItem(at: folder)
        try! FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)

        let unread = PrintSelection.spool(job, directory: folder.path, cancelAfter: -1, rasters: [missing])
        precondition(!unread.success)
        precondition(!unread.openedViewer)
        precondition(unread.usedDatabaseRaster)
        precondition(unread.refusal == PrintSelection.unreadableEntryRefusal(title: "Axial"))
        precondition(unread.pages.isEmpty)

        let ok = PrintSelection.spool(job, directory: folder.path, cancelAfter: -1, rasters: [tall])
        precondition(ok.success)
        precondition(!ok.openedViewer)
        precondition(ok.usedDatabaseRaster)
        precondition(ok.pages.count == 1)
        precondition(ok.pages[0].url!.lastPathComponent == "page-0000.pdf")
        precondition(!PrintSelection.temporaryNameLeaksIdentifiers(ok.pages[0].url!.lastPathComponent,
                                                                  patientName: "DOE^JOHN", patientID: "12345"))
        let written = try! Data(contentsOf: ok.pages[0].url!)
        let writtenBox = PrintSelection.mediaBox(in: written)
        precondition(writtenBox.width == 10 && writtenBox.height == 20)

        let twoA = PrintEntry(); twoA.title = "A"
        let twoB = PrintEntry(); twoB.title = "B"
        job.entries = [twoA, twoB]
        let cancelled = PrintSelection.spool(job, directory: folder.path, cancelAfter: 1,
                                             rasters: [tall, tall])
        precondition(cancelled.cancelled)
        precondition(!cancelled.success)
        precondition(cancelled.pages.count == 1)
        precondition(cancelled.refusal == PrintSelection.cancelledRefusal)

        print("PASS: #384 A database spool writes as-stored PDF pages without a viewer")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-print-spool-') as folder:
    path = Path(folder)
    (path / 'check.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                    str(path / 'check.swift'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
