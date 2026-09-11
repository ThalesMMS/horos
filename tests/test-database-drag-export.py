#!/usr/bin/env python3
"""Batch file promises for database rows and thumbnails (#605), object level.

Compiles `Horos/Sources/DatabaseDragExport.swift` with AppKit and a driver:
the promised folder is named safely for one or several items; series folders,
image and report file names are numbered in export order; a report series is
a Structured Report or an encapsulated PDF and never one of the application's
own SRs; a single-record multiframe series expands only when the whole series
was dragged; the promise advertises the folder and, for DICOM drags only, the
database object identifiers so albums and Sources keep working; its writer is
called with the drop URL and delivers the completion; staging commits whole,
never over an existing destination, and discards only what it created; every
pasteboard item's identifiers are read, not just the first.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/DatabaseDragExport.swift'
failures = []
if 'DatabaseDragExport.swift in Sources' not in (root / 'Horos.xcodeproj/project.pbxproj').read_text():
    failures.append('DatabaseDragExport.swift is not in the Horos target')

DRIVER = r'''
import AppKit
func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); exit(1) } }
_ = NSApplication.shared

// 1. Names.
expect(BatchExportPlan.exportName(itemNames: ["CT Head"], asJPEG: false) == "CT Head", "one DICOM item keeps its name")
expect(BatchExportPlan.exportName(itemNames: ["CT Head"], asJPEG: true) == "CT Head - Export", "a JPEG export says so")
expect(BatchExportPlan.exportName(itemNames: ["a", "b"], asJPEG: false) == "DICOM Export", "several items share a generic name")
expect(BatchExportPlan.exportName(itemNames: ["a", "b"], asJPEG: true) == "Image and Report Export", "several JPEG items share a generic name")
expect(BatchExportPlan.exportName(itemNames: ["DOE/JANE: \"x\""], asJPEG: false) == "DOE JANE x", "hostile characters are replaced: \(BatchExportPlan.exportName(itemNames: ["DOE/JANE: \"x\""], asJPEG: false))")
expect(!BatchExportPlan.exportName(itemNames: [".hidden"], asJPEG: false).hasPrefix("."), "a leading dot would hide the folder")
expect(BatchExportPlan.exportName(itemNames: [String(repeating: "x", count: 300)], asJPEG: false).count <= 100, "names are capped")
expect(BatchExportPlan.exportName(itemNames: [""], asJPEG: false) == "DICOM Export", "an empty name falls back")
expect(BatchExportPlan.seriesDirectoryName(index: 3, seriesName: "T1/axial") == "0003 - T1 axial", "series folders are numbered and sanitized")
expect(BatchExportPlan.seriesDirectoryName(index: 1, seriesName: nil) == "0001 - Series", "a nameless series is still a folder")
expect(BatchExportPlan.imageFileName(index: 7, frame: 0) == "IM-000007-000001.jpg", "image names carry index and frame")
expect(BatchExportPlan.reportFileName(index: 2) == "Report-000002.pdf", "report names carry the index")

// 2. Reports and internal state.
expect(BatchExportPlan.isReportSeries(name: "Report", sopClassUID: "1.2.840.10008.5.1.4.1.1.88.11", modality: "SR"), "a basic text SR is a report")
expect(BatchExportPlan.isReportSeries(name: "Doc", sopClassUID: "1.2.840.10008.5.1.4.1.1.104.1", modality: "OT"), "an encapsulated PDF is a report")
expect(BatchExportPlan.isReportSeries(name: "x", sopClassUID: "", modality: "pdf"), "modality PDF is a report")
for stateName in BatchExportPlan.internalStateSeriesNames {
    expect(!BatchExportPlan.isReportSeries(name: stateName, sopClassUID: "1.2.840.10008.5.1.4.1.1.88.11", modality: "SR"), "\(stateName) is application state, not a report")
}
expect(!BatchExportPlan.isReportSeries(name: "CT", sopClassUID: "1.2.840.10008.5.1.4.1.1.2", modality: "CT"), "a CT series is not a report")
expect(BatchExportPlan.includesInJPEGExport(imageStorage: false, reportSeries: true), "reports are included in a JPEG export")
expect(!BatchExportPlan.includesInJPEGExport(imageStorage: false, reportSeries: false), "a non-image, non-report instance is skipped")

// 3. Multiframe expansion.
expect(BatchExportPlan.frameCount(numberOfFrames: 30, seriesImageCount: 1, wholeSeries: true) == 30, "a single-record multiframe series expands when dragged whole")
expect(BatchExportPlan.frameCount(numberOfFrames: 30, seriesImageCount: 30, wholeSeries: true) == 1, "a series indexed frame by frame is not written again per frame")
expect(BatchExportPlan.frameCount(numberOfFrames: 30, seriesImageCount: 1, wholeSeries: false) == 1, "a single dragged thumbnail exports one frame")

// 4. The promise.
let folder = DatabaseFilePromise.folderPromise()
folder.exportName = "CT Head"
folder.objectXIDs = try! PropertyListSerialization.data(fromPropertyList: ["x-coredata://A/B/p1"], format: .binary, options: 0)
folder.extraTypes = ["com.horos.dbobjectxids"]
let pasteboard = NSPasteboard(name: NSPasteboard.Name("horos-test-\(UUID().uuidString)"))
let types = folder.writableTypes(for: pasteboard).map { $0.rawValue }
expect(types.contains("com.horos.dbobjectxids"), "a DICOM promise carries the object identifiers: \(types)")
expect(types.contains(where: { $0.contains("promised-file") || $0.contains("file-promise") || $0 == "com.apple.NSFilePromiseItemMetaData" }), "the promise advertises itself: \(types)")
let jpeg = DatabaseFilePromise.jpegPromise()
expect(!jpeg.writableTypes(for: pasteboard).map({ $0.rawValue }).contains("com.horos.dbobjectxids"), "a JPEG promise carries no identifiers")
expect(folder.filePromiseProvider(folder, fileNameForType: "public.folder") == "CT Head", "the promised name is the export name")

let base = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("horos-batch-drag-\(UUID().uuidString)", isDirectory: true)
try! FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: base) }
var written: URL?
folder.setWriter { url, completion in written = url; completion(nil) }
var completed = false
folder.filePromiseProvider(folder, writePromiseTo: base.appendingPathComponent("CT Head"), completionHandler: { error in completed = error == nil })
expect(written?.lastPathComponent == "CT Head" && completed && folder.promiseWritten, "the writer receives the drop URL and completes")
var noWriterError: Error?
DatabaseFilePromise.folderPromise().filePromiseProvider(folder, writePromiseTo: base.appendingPathComponent("x"), completionHandler: { noWriterError = $0 })
expect(noWriterError != nil, "a promise without a writer fails explicitly")

// 4b. The completion guard: fires once, and fires cancellation when dropped unfired.
var guardCalls: [Int] = []
let fired = PromiseCompletionGuard { error in guardCalls.append(error == nil ? 0 : (error! as NSError).code) }
fired.fire(error: nil); fired.fire(error: NSError(domain: NSCocoaErrorDomain, code: 1, userInfo: nil))
expect(guardCalls == [0] && fired.hasFired, "the guard delivers once: \(guardCalls)")
do {
    let dropped = PromiseCompletionGuard { error in guardCalls.append((error! as NSError).code) }
    expect(!dropped.hasFired, "an unfired guard is still armed")
}
expect(guardCalls == [0, NSUserCancelledError], "a guard released without firing reports cancellation: \(guardCalls)")
// A thread cancelled before it starts never runs; the watched guard still answers.
var watched: Int?
let watchedGuard = PromiseCompletionGuard { error in watched = (error as NSError?)?.code ?? 0 }
let never = Thread { fatalError("a cancelled thread must not run") }
never.cancel(); never.start()
watchedGuard.watch(thread: never)
let deadline = Date().addingTimeInterval(3)
while watched == nil && Date() < deadline { RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.05)) }
expect(watched == NSUserCancelledError, "a never-started worker reports cancellation to the drop: \(String(describing: watched))")
withExtendedLifetime(watchedGuard) {}

// 5. Staging.
let destination = base.appendingPathComponent("Export")
let staging = try! ExportStaging.stagingDirectory(for: destination)
expect(FileManager.default.fileExists(atPath: staging.path), "staging exists")
expect(!ExportStaging.stagingHasContent(staging), "an empty staging has no content")
try! Data([1, 2, 3]).write(to: staging.appendingPathComponent("IM-000001-000001.jpg"))
expect(ExportStaging.stagingHasContent(staging), "a written file is content")
try! ExportStaging.commit(staging: staging, to: destination)
expect(FileManager.default.fileExists(atPath: destination.appendingPathComponent("IM-000001-000001.jpg").path), "the export moved whole into place")
expect(!FileManager.default.fileExists(atPath: staging.path), "staging is gone after the move")
let staging2 = try! ExportStaging.stagingDirectory(for: destination)
try! Data([9]).write(to: staging2.appendingPathComponent("other.jpg"))
var refused = false
do { try ExportStaging.commit(staging: staging2, to: destination) } catch { refused = true }
expect(refused, "an existing destination is never overwritten")
expect(FileManager.default.fileExists(atPath: destination.appendingPathComponent("IM-000001-000001.jpg").path), "the earlier export is untouched")
let bystander = staging2.deletingLastPathComponent().appendingPathComponent("someone-else")
try! FileManager.default.createDirectory(at: bystander, withIntermediateDirectories: true)
ExportStaging.discard(staging: staging2)
expect(!FileManager.default.fileExists(atPath: staging2.path), "discard removes the staging")
expect(FileManager.default.fileExists(atPath: bystander.path), "discard leaves another export's directory alone")
try? FileManager.default.removeItem(at: bystander)

// 6. Identifiers across pasteboard items.
let pb = NSPasteboard(name: NSPasteboard.Name("horos-xids-\(UUID().uuidString)"))
pb.clearContents()
let type = NSPasteboard.PasteboardType("com.horos.dbobjectxids")
let items: [NSPasteboardItem] = ["a", "b", "b"].map { xid in
    let item = NSPasteboardItem()
    item.setPropertyList(try! PropertyListSerialization.data(fromPropertyList: [xid], format: .binary, options: 0), forType: type)
    return item
}
pb.writeObjects(items)
let ids = PasteboardObjectIdentifiers.identifiers(on: pb, types: ["com.horos.dbobjectxids"])
expect(ids == ["a", "b"], "every item's identifiers are read once: \(ids)")
expect(PasteboardObjectIdentifiers.identifiers(on: pb, types: ["nothing"]).isEmpty, "an absent type yields nothing")
print("ok: batch drag export names, reports, frames, promise, staging and identifiers")
'''

if not failures:
    with tempfile.TemporaryDirectory() as tmp:
        driver = Path(tmp) / 'main.swift'
        driver.write_text(DRIVER)
        binary = Path(tmp) / 'driver'
        build = subprocess.run(['xcrun', 'swiftc', str(source), str(driver), '-o', str(binary)], capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('driver did not compile:\n' + build.stderr[-3000:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip() or 'driver failed without output')
            else:
                print(run.stdout.strip())

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
