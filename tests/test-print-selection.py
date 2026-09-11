#!/usr/bin/env python3
"""Database print uses the effective selection, not the outline table (#384 A)."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/PrintSelection.swift'
assert source.is_file(), 'FAIL: PrintSelection.swift is missing'

driver = r'''
import Foundation

@main struct Check {
    static let ct = PrintSelection.ctImageStorage
    static let sr = PrintSelection.basicTextSR
    static let pdf = PrintSelection.encapsulatedPDF

    static func image(_ path: String, frames: Int = 1, count: Int = 1, kind: String = "series") -> PrintRecord {
        PrintRecord(kind: kind, seriesSOPClassUID: ct, modality: "CT", seriesName: "Axial",
                    path: path, imageCount: count, numberOfFrames: frames, parentIsStudy: true)
    }

    static func main() {
        precondition(!PrintSelection.mayPrintOutlineView())
        precondition(!PrintSelection.replacesReportEditors())
        precondition(!PrintSelection.replacesDICOMFilmPrint())
        precondition(!PrintSelection.implementsRegisteredGIF())
        precondition(!PrintSelection.autoRotatesPages())
        precondition(PrintSelection.gifBlockedOnRegistration.contains("#378"))

        let empty = PrintSelection.job(from: [], source: "effective")
        precondition(empty.refusal == PrintSelection.emptySelectionRefusal)
        precondition(!empty.success)

        let table = PrintSelection.job(from: [image("/tmp/a.dcm")], source: "databaseTable")
        precondition(table.printedDatabaseTable)
        precondition(table.refusal.contains("effective selection"))
        precondition(!table.success)

        let one = PrintRecord(kind: "image", seriesSOPClassUID: ct, modality: "CT", seriesName: "Axial",
                              path: "/tmp/ct.dcm", imageCount: 1, numberOfFrames: 1, parentIsStudy: false)
        let job = PrintSelection.job(from: [one], source: "effective")
        precondition(job.success)
        precondition(job.usedEffectiveSelection)
        precondition(job.entries.count == 1)
        precondition(job.entries[0].frame == 0)
        precondition(!job.entries[0].isReport)

        // Study selection skips OsiriX annotation archives.
        let archive = PrintRecord(kind: "series", seriesSOPClassUID: ct, modality: "OT",
                                  seriesName: "OsiriX ROI", path: "/tmp/roi.dcm", imageCount: 1,
                                  numberOfFrames: 1, parentIsStudy: true)
        let skipped = PrintSelection.job(from: [archive], source: "effective")
        precondition(skipped.refusal == PrintSelection.emptySelectionRefusal)

        let report = PrintRecord(kind: "series", seriesSOPClassUID: sr, modality: "SR", seriesName: "Report",
                                  path: "/tmp/sr.dcm", imageCount: 1, numberOfFrames: 1, parentIsStudy: true)
        let pdfItem = PrintRecord(kind: "series", seriesSOPClassUID: pdf, modality: "PDF", seriesName: "PDF",
                                  path: "/tmp/a.pdf", imageCount: 1, numberOfFrames: 1, parentIsStudy: true)
        let reports = PrintSelection.job(from: [report, pdfItem], source: "effective")
        precondition(reports.entries.count == 2)
        precondition(reports.entries.allSatisfy(\.isReport))

        // Whole-series single DB row with 8 frames expands; a single image does not.
        let series = PrintRecord(kind: "series", seriesSOPClassUID: ct, modality: "CT", seriesName: "US",
                                  path: "/tmp/mf.dcm", imageCount: 1, numberOfFrames: 8, parentIsStudy: true)
        let expanded = PrintSelection.job(from: [series], source: "effective")
        precondition(expanded.entries.count == 8)
        precondition(expanded.entries[7].frame == 7)
        let single = PrintRecord(kind: "image", seriesSOPClassUID: ct, modality: "CT", seriesName: "US",
                                  path: "/tmp/mf.dcm", imageCount: 1, numberOfFrames: 8, parentIsStudy: false)
        single.frameID = 3
        let oneFrame = PrintSelection.job(from: [single], source: "effective")
        precondition(oneFrame.entries.count == 1)
        precondition(oneFrame.entries[0].frame == 3)

        let cancelled = PrintSelection.prepare(expanded, cancelAfter: 2)
        precondition(cancelled.cancelled)
        precondition(!cancelled.success)
        precondition(cancelled.preparedCount == 2)
        precondition(cancelled.refusal == PrintSelection.cancelledRefusal)

        let done = PrintSelection.prepare(job, cancelAfter: 99)
        precondition(done.success)
        precondition(!done.cancelled)

        let page = PrintSelection.pageTemporaryName(index: 3, patientName: "DOE^JOHN")
        precondition(page == "page-0003.pdf")
        precondition(!PrintSelection.temporaryNameLeaksIdentifiers(page, patientName: "DOE^JOHN", patientID: "12345"))
        precondition(PrintSelection.temporaryNameLeaksIdentifiers("DOE^JOHN-page.pdf", patientName: "DOE^JOHN", patientID: ""))
        // Frame order across the whole run, not just its last entry: a page out
        // of order or a repeated frame is the duplication the case forbids.
        precondition(expanded.entries.map(\.frame) == Array(0..<8))
        precondition(expanded.entries.allSatisfy { $0.frameCount == 8 })
        precondition(Set(expanded.entries.map(\.frame)).count == 8)

        // Partial selection: what is not printable is dropped, what is stays in
        // order, and the job still says it came from the effective selection.
        let mixed = PrintSelection.job(from: [archive, one, report, series], source: "effective")
        precondition(mixed.success)
        precondition(mixed.usedEffectiveSelection)
        precondition(mixed.entries.count == 1 + 1 + 8)
        precondition(!mixed.entries[0].isReport)
        precondition(mixed.entries[1].isReport)
        precondition(mixed.entries[2...].map(\.frame) == Array(0..<8))

        // Cancelling inside a multiframe expansion keeps a prefix, never a gap,
        // and never reports success.
        let stopped = PrintSelection.prepare(expanded, cancelAfter: 3)
        precondition(stopped.cancelled)
        precondition(!stopped.refusal.isEmpty)
        precondition(stopped.entries.map(\.frame) == [0, 1, 2])
        let notStopped = PrintSelection.prepare(expanded, cancelAfter: -1)
        precondition(!notStopped.cancelled)
        precondition(notStopped.entries.count == 8)

        precondition(PrintSelection.unreadableEntryRefusal(title: "Axial").contains("Axial"))
        precondition(!PrintSelection.isPrintableSeries(sopClassUID: "1.2.840.10008.5.1.4.1.1.11.1",
                                                        modality: "PR", name: "GSPS", parentIsStudy: true))

        print("PASS: #384 A effective selection, skip archives, expand frames in order, partial selection, cancel mid-expansion, no PHI in temp names")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='horos-print-selection-') as folder:
    path = Path(folder)
    (path / 'check.swift').write_text(driver)
    subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                    str(path / 'check.swift'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
