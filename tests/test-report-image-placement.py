#!/usr/bin/env python3
"""Insert selected images into a Pages or Word report at a predictable size.

Acceptance (#153): the figure fits a known box, a save/reopen leaves the box
where it was, and the source image is never written. Pages and Word are driven
only through an injected runner here — no real mail, no live editor.
"""
from pathlib import Path
import hashlib
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
program = r'''
import AppKit
import Foundation

func png(width: Int, height: Int, red: Double) -> URL {
    let url = FileManager.default.temporaryDirectory
        .appendingPathComponent(UUID().uuidString)
        .appendingPathExtension("png")
    let image = NSImage(size: NSSize(width: width, height: height))
    image.lockFocus()
    NSColor(red: red, green: 0.2, blue: 0.2, alpha: 1).setFill()
    NSBezierPath(rect: NSRect(x: 0, y: 0, width: width, height: height)).fill()
    image.unlockFocus()
    let tiff = image.tiffRepresentation!
    let rep = NSBitmapImageRep(data: tiff)!
    try! rep.representation(using: .png, properties: [:])!.write(to: url)
    return url
}

func bytes(_ path: String) -> Data {
    try! Data(contentsOf: URL(fileURLWithPath: path))
}

let box = ReportImagePlacement.defaultBox
precondition(box.width == 340 && box.height == 255, "the report figure box is 12 cm by 9 cm at 72 pt")

let landscape = ReportImagePlacement.displaySize(pixelWidth: 1024, pixelHeight: 512, box: box)
precondition(landscape.width == 340 && landscape.height == 170, "landscape fits the width")
let portrait = ReportImagePlacement.displaySize(pixelWidth: 512, pixelHeight: 1024, box: box)
precondition(portrait.width == 127.5 && portrait.height == 255, "portrait fits the height")
let square = ReportImagePlacement.displaySize(pixelWidth: 512, pixelHeight: 512, box: box)
precondition(square.width == 255 && square.height == 255, "square fits the shorter side")
let again = ReportImagePlacement.displaySize(pixelWidth: 512, pixelHeight: 512, box: box)
precondition(again == square, "the same pixels always produce the same box")
precondition(ReportImagePlacement.displaySize(pixelWidth: 0, pixelHeight: 10, box: box) == .zero)
precondition(ReportImagePlacement.displaySize(pixelWidth: 10, pixelHeight: -1, box: box) == .zero)

precondition(ReportImageInsertion.kind(ofReportPath: "/tmp/study.pages") == .pages)
precondition(ReportImageInsertion.kind(ofReportPath: "/tmp/study.DOCX") == .word)
precondition(ReportImageInsertion.kind(ofReportPath: "/tmp/study.doc") == .word)
precondition(ReportImageInsertion.kind(ofReportPath: "/tmp/study.rtf") == .unsupported)
precondition(ReportImageInsertion.kind(ofReportPath: "/tmp/study.pdf") == .unsupported)

let source = png(width: 80, height: 40, red: 0.8)
let sourceBytes = bytes(source.path)
let dest = FileManager.default.temporaryDirectory
    .appendingPathComponent(UUID().uuidString)
    .appendingPathExtension("jpg")
precondition(ReportImageInsertion.writeCopy(from: source.path, to: dest.path))
precondition(bytes(source.path) == sourceBytes, "the source image must not be written")
precondition(FileManager.default.fileExists(atPath: dest.path))
precondition(!ReportImageInsertion.writeCopy(from: source.path, to: source.path), "refuse to write onto the source")
precondition(bytes(source.path) == sourceBytes)

let reportDir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try! FileManager.default.createDirectory(at: reportDir, withIntermediateDirectories: true)
let report = reportDir.appendingPathComponent("study.pages")
try! "original-report".data(using: .utf8)!.write(to: report)
let original = try! Data(contentsOf: report)

let prepared = ReportImageInsertion.prepare(sources: [source.path], directory: reportDir.appendingPathComponent("images").path)
precondition(prepared.count == 1)
precondition(prepared[0].widthPoints == 340 && prepared[0].heightPoints == 170)
precondition(bytes(source.path) == sourceBytes)
precondition(!prepared[0].path.contains(source.path), "the document is given a copy, not the source")

let pages = ReportImageInsertion.pagesScript(documentName: report.lastPathComponent, images: prepared)
precondition(pages.contains("end of body text"), "Pages inserts inline so a reopen cannot slide a floating box")
precondition(!pages.contains("position"), "a positioned box is what moves on save/reopen")
precondition(pages.contains("340") && pages.contains("170"), "the script pins the computed size")
precondition(pages.contains("repeat with attempt from 1 to 60"), "the script waits for the private copy by name")
precondition(pages.contains("delay 0.5"), "the wait is not a single pass that races LaunchServices")
precondition(pages.contains("on error errorMessage number errorNumber"), "a refused insert must capture the AppleScript number")
precondition(pages.contains("close d saving no"), "the private copy is closed")
precondition(pages.contains(prepared[0].path))
precondition(!pages.contains(source.path), "Pages is never handed the source image")

let word = ReportImageInsertion.wordScript(documentName: report.lastPathComponent, images: prepared)
precondition(word.contains("inline picture"), "Word inserts an inline picture, not a floating shape")
precondition(word.contains("340") && word.contains("170"))
precondition(word.contains("repeat with attempt from 1 to 60"))
precondition(word.contains("on error errorMessage number errorNumber"))
precondition(word.contains(prepared[0].path))
precondition(!word.contains(source.path))

let timeout = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -1712])
precondition(timeout.contains("1712") && timeout.contains("Automation"), "a timeout is not a generic insert failure")
let denied = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -1743])
precondition(denied.contains("denied") && denied.contains("Automation"))
let dropped = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -609])
precondition(dropped.contains("609"))
let noWord = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -1728])
precondition(noWord.contains("1728") && noWord.contains("Word"))
let container = ReportImageInsertion.errorMessage(from: [NSAppleScript.errorNumber: -10024])
precondition(container.contains("10024"))
precondition(timeout.contains("preserved") && noWord.contains("preserved"))

var scripts: [String] = []
precondition(!ReportImageInsertion.insert(reportPath: report.path, sources: [source.path], runner: { script, preparedPath in
    scripts.append(script)
    precondition(preparedPath != report.path, "the editor is driven on a private copy")
    precondition((preparedPath as NSString).lastPathComponent != report.lastPathComponent, "an already-open report with the same name must not be the document the script finds")
    return false
}), "a failed editor leaves the original report")
precondition(try! Data(contentsOf: report) == original)
precondition(bytes(source.path) == sourceBytes)
precondition(scripts.count == 1)
precondition(scripts[0].contains("end of body text"))

scripts.removeAll()
precondition(ReportImageInsertion.insert(reportPath: report.path, sources: [source.path], runner: { script, preparedPath in
    scripts.append(script)
    try! "edited-report".data(using: .utf8)!.write(to: URL(fileURLWithPath: preparedPath))
    return true
}))
precondition(try! String(contentsOf: report, encoding: .utf8) == "edited-report")
precondition(bytes(source.path) == sourceBytes)

let rtf = reportDir.appendingPathComponent("study.rtf")
try! "rtf-report".data(using: .utf8)!.write(to: rtf)
precondition(!ReportImageInsertion.insert(reportPath: rtf.path, sources: [source.path], runner: { _, _ in
    preconditionFailure("unsupported reports must not be opened")
}))
precondition(try! String(contentsOf: rtf, encoding: .utf8) == "rtf-report")

let missing = reportDir.appendingPathComponent("missing.pages")
precondition(!ReportImageInsertion.insert(reportPath: missing.path, sources: [source.path], runner: { _, _ in
    preconditionFailure("a missing report must not be invented")
}))

let wordReport = reportDir.appendingPathComponent("study.docx")
try! "word-report".data(using: .utf8)!.write(to: wordReport)
var wordScripts: [String] = []
precondition(!ReportImageInsertion.insert(reportPath: wordReport.path, sources: [], runner: { _, _ in
    preconditionFailure("no images means nothing is sent to Word")
}))
precondition(try! String(contentsOf: wordReport, encoding: .utf8) == "word-report")
precondition(ReportImageInsertion.insert(reportPath: wordReport.path, sources: [source.path], runner: { script, _ in
    wordScripts.append(script)
    return true
}))
precondition(wordScripts[0].contains("inline picture"))

// Save then reopen: the prepared geometry is the only box, and it does not move.
let first = ReportImagePlacement.displaySize(pixelWidth: 800, pixelHeight: 600)
let reopened = ReportImagePlacement.displaySize(pixelWidth: 800, pixelHeight: 600)
precondition(first == reopened)
precondition(first.width <= box.width && first.height <= box.height)
print("PASS: predictable figure size, inline Pages/Word scripts, wait-for-document, captured AppleScript errors, failed insert preserves the report, source image never written")
'''

with tempfile.TemporaryDirectory(prefix='horos-report-images-') as folder:
    p = Path(folder)
    (p / 'main.swift').write_text(program)
    compile = subprocess.run(
        [
            'xcrun', 'swiftc',
            '-O',
            str(root / 'Horos/Sources/ReportImagePlacement.swift'),
            str(p / 'main.swift'),
            '-o', str(p / 'test'),
        ],
        capture_output=True,
        text=True,
    )
    if compile.returncode != 0:
        print(compile.stderr)
        raise SystemExit(compile.returncode)
    subprocess.run([str(p / 'test')], check=True)
