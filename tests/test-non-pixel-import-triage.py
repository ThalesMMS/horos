#!/usr/bin/env python3
"""Objects without a picture pass the incoming gate on their own terms (#605).

The incoming triage refused any DICOM object without Rows/Columns as an image
"0 by 0 which the thumbnail stack cannot load" — Structured Reports excepted —
so a valid encapsulated PDF, presentation state, RT structure set or waveform
went to NOT READABLE instead of the database, while the DICOM reader itself
accepts them. Compiles the real triage with synthetic explicit-VR files built
in memory: an encapsulated PDF and a presentation state are merged, a zero-size
CT is still refused, and an image class without pixel data is still an image
with a problem, not a report.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
sources = [root / 'Horos/Sources/EnhancedImportTriage.swift', root / 'Horos/Sources/DICOMTriageMetadata.swift']
failures = []

DRIVER = r'''
import Foundation
func expect(_ ok: Bool, _ reason: String) { if !ok { print("FAIL: " + reason); exit(1) } }

func element(_ group: UInt16, _ element: UInt16, _ vr: String, _ value: Data) -> Data {
    var out = Data()
    func le16(_ v: UInt16) { out.append(UInt8(v & 0xff)); out.append(UInt8(v >> 8)) }
    func le32(_ v: UInt32) { for i in 0..<4 { out.append(UInt8((v >> (8 * UInt32(i))) & 0xff)) } }
    var padded = value
    if padded.count % 2 == 1 { padded.append(vr == "UI" ? 0 : 0x20) }
    le16(group); le16(element); out.append(contentsOf: vr.utf8)
    if ["OB", "OW", "SQ", "UN", "UT"].contains(vr) { le16(0); le32(UInt32(padded.count)) } else { le16(UInt16(padded.count)) }
    out.append(padded)
    return out
}
func uiElement(_ g: UInt16, _ e: UInt16, _ s: String) -> Data { element(g, e, "UI", Data(s.utf8)) }
func usElement(_ g: UInt16, _ e: UInt16, _ v: UInt16) -> Data { element(g, e, "US", Data([UInt8(v & 0xff), UInt8(v >> 8)])) }
func file(_ dataset: Data) -> Data {
    var out = Data(count: 128); out.append(contentsOf: "DICM".utf8)
    out.append(uiElement(0x0002, 0x0010, "1.2.840.10008.1.2.1"))
    out.append(dataset)
    return out
}
let directory = FileManager.default.temporaryDirectory.appendingPathComponent("triage-" + UUID().uuidString)
try! FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: directory) }
func write(_ name: String, _ data: Data) -> String { let p = directory.appendingPathComponent(name).path; try! data.write(to: URL(fileURLWithPath: p)); return p }

let pdfBytes = Data("%PDF-1.4 synthetic".utf8)
let pdf = write("pdf.dcm", file(uiElement(0x0008, 0x0016, "1.2.840.10008.5.1.4.1.1.104.1") + element(0x0042, 0x0011, "OB", pdfBytes)))
let pdfAssessment = EnhancedImportTriage.assessPath(pdf)
expect(pdfAssessment.detectedDICOM, "the encapsulated PDF is DICOM")
expect(pdfAssessment.mayMergeIntoIncoming, "an encapsulated PDF is merged into incoming: \(pdfAssessment.recordedError ?? "")")
expect(pdfAssessment.thumbnailCompatible, "an encapsulated PDF does not claim a broken thumbnail")

let pr = write("pr.dcm", file(uiElement(0x0008, 0x0016, "1.2.840.10008.5.1.4.1.1.11.1")))
expect(EnhancedImportTriage.assessPath(pr).mayMergeIntoIncoming, "a presentation state is merged")

let sr = write("sr.dcm", file(uiElement(0x0008, 0x0016, "1.2.840.10008.5.1.4.1.1.88.11")))
expect(EnhancedImportTriage.assessPath(sr).mayMergeIntoIncoming, "a structured report is still merged")

let zeroCT = write("ct0.dcm", file(uiElement(0x0008, 0x0016, "1.2.840.10008.5.1.4.1.1.2") + usElement(0x0028, 0x0010, 0) + usElement(0x0028, 0x0011, 0) + usElement(0x0028, 0x0100, 16)))
let zero = EnhancedImportTriage.assessPath(zeroCT)
expect(!zero.mayMergeIntoIncoming, "a zero-size CT is still refused")
expect(zero.recordedError?.contains("0 by 0") == true, "the refusal still says why: \(zero.recordedError ?? "")")

let noPixelCT = write("ct-nopix.dcm", file(uiElement(0x0008, 0x0016, "1.2.840.10008.5.1.4.1.1.2") + usElement(0x0028, 0x0010, 8) + usElement(0x0028, 0x0011, 8) + usElement(0x0028, 0x0100, 16)))
let noPixel = EnhancedImportTriage.assessPath(noPixelCT)
expect(noPixel.mayMergeIntoIncoming && noPixel.recordedError == "carries no Pixel Data element", "an image class without pixels is kept with its problem recorded: \(noPixel.recordedError ?? "")")

let pdfWithPixels = write("pdf-pix.dcm", file(uiElement(0x0008, 0x0016, "1.2.840.10008.5.1.4.1.1.104.1") + usElement(0x0028, 0x0010, 0) + usElement(0x0028, 0x0011, 0) + element(0x7fe0, 0x0010, "OB", Data([1, 2]))))
expect(!EnhancedImportTriage.assessPath(pdfWithPixels).mayMergeIntoIncoming, "a PDF class that claims pixel data of size 0 by 0 is judged as an image")
print("ok: non-pixel storage classes pass the incoming gate; zero-size images still do not")
'''

with tempfile.TemporaryDirectory() as tmp:
    driver = Path(tmp) / 'main.swift'
    driver.write_text(DRIVER)
    binary = Path(tmp) / 'driver'
    build = subprocess.run(['xcrun', 'swiftc'] + [str(s) for s in sources] + [str(driver), '-o', str(binary)], capture_output=True, text=True)
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
