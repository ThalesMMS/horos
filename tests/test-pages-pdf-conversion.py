#!/usr/bin/env python3
"""Pages → PDF keeps the report and associates the DICOM with the study.

Horos issue 560 / workbench #129: Pages 10 on RC4 no longer produced a DICOM
PDF, neither from File > Report > Convert to DICOM PDF nor from marking the
study Validated. The AppleScript still said `tell application "Pages"` and
`open` of a path, which a sandboxed Pages answers without opening anything;
export then failed or wrote nothing, and a missing source DICOM left the
encapsulated PDF without the study's StudyInstanceUID.

The original .pages is never the export destination. A conversion that cannot
run leaves that file and its reportURL alone, and nothing is imported.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

conversion = root / 'Horos/Sources/PagesPDFConversion.swift'
if not conversion.is_file():
    failures.append('Horos/Sources/PagesPDFConversion.swift is missing')
    print('FAIL: Horos/Sources/PagesPDFConversion.swift is missing')
    sys.exit(1)

source = conversion.read_text()
report_mm = (root / 'Horos/Sources/DicomStudy+Report.mm').read_bytes().decode('latin1')
report_h = (root / 'Horos/Sources/DicomStudy+Report.h').read_bytes().decode('latin1')
study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text()

if 'NSWorkspace.shared.open' not in source:
    failures.append('Pages is not granted the report through LaunchServices')
if 'tell application "Pages"' in source:
    failures.append('the converter still names Pages by localized name')
if 'application id' not in source:
    failures.append('the converter does not talk to Pages by bundle identifier')
if 'com.apple.iWork.Pages' not in source or '"com.apple.Pages"' not in source:
    failures.append('the converter does not restrict itself to Apple Pages')
if 'Finder' in source:
    failures.append('Finder is still asked to delete the destination')
if 'copyItem' not in source and 'copyItemAtPath' not in source:
    failures.append('the converter edits the original report instead of a working copy')
if 'saving no' not in source and 'saving: no' not in source:
    failures.append('the working copy is saved back, which can rewrite a Pages document')
if 'DispatchSemaphore' in source or 'semaphore' in source.lower():
    failures.append("the main thread waits on NSWorkspace's completion handler")

pages_branch = report_mm[report_mm.find('isEqualToString:@"pages"'):]
pages_branch = pages_branch[:pages_branch.find('else if')]
if 'HorosPagesPDFConversion' not in pages_branch:
    failures.append('the Pages branch still runs the old AppleScript instead of HorosPagesPDFConversion')
if 'pages2pdf' in pages_branch or 'pages092pdf' in pages_branch:
    failures.append('the Pages branch still launches pages2pdf.applescript')
if 'Horos-Swift.h' not in report_mm:
    failures.append('DicomStudy+Report.mm cannot see the Swift converter')
if 'isUsablePDFAtPath' not in report_mm:
    failures.append('a missing or empty PDF can still be encapsulated')
if 'associationAttributesWithStudyInstanceUID' not in report_mm:
    failures.append('the encapsulated PDF is not given the study StudyInstanceUID')
if 'studyInstanceUID' not in report_mm[report_mm.find('transformPdfAtPath:(NSString*)pdfPath toDicomAtPath:'):]:
    failures.append('the instance PDF→DICOM path does not read the study UID')

validated = study[study.find('generateDICOMPDFWhenValidated'):]
validated = validated[:validated.find('@catch (NSException * e)')]
if 'fileExistsAtPath' not in validated and 'isUsablePDF' not in validated:
    failures.append('Validated still imports a path even when conversion wrote nothing')
if 'reportURL' in validated and 'setValue' in validated:
    failures.append('Validated rewrites reportURL when making the PDF')

manual = browser[browser.find('- (IBAction) convertReportToDICOMSR:'):]
manual = manual[:manual.find('- (IBAction) convertReportToPDF:')]
if 'fileExistsAtPath' not in manual:
    failures.append('the manual DICOM PDF action still imports a path conversion did not write')
if 'saveReportAsDicomAtPath' not in manual:
    failures.append('the manual action no longer shares saveReportAsDicomAtPath with Validated')

if 'PagesPDFConversion.swift' not in pbx:
    failures.append('PagesPDFConversion.swift is not in the Xcode project')

program = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func expect(_ condition: Bool, _ message: String) {
    if !condition { fail(message) }
}

let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let report = directory.appendingPathComponent("report.pages")
let pdf = directory.appendingPathComponent("report.pdf")
let original = Data("synthetic pages report, do not replace".utf8)
try original.write(to: report)

expect(!PagesPDFConversion.isUsablePDF(at: pdf.path), "a missing file is not a PDF")
try Data("%PDF".utf8).write(to: pdf)
expect(!PagesPDFConversion.isUsablePDF(at: pdf.path), "a truncated header is not a usable PDF")
try Data("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n".utf8).write(to: pdf)
expect(PagesPDFConversion.isUsablePDF(at: pdf.path), "a tiny one-page PDF must be accepted")
try FileManager.default.removeItem(at: pdf)

var error: NSError?
expect(!PagesPDFConversion.convertReport(at: report.path, toPDFAt: report.path, error: &error),
       "exporting onto the report itself must be refused")
expect((try Data(contentsOf: report)) == original, "refusing same-path overwrote the report")
expect(!FileManager.default.fileExists(atPath: pdf.path), "a refused conversion left a PDF")

let inside = report.appendingPathComponent("Preview.pdf")
error = nil
expect(!PagesPDFConversion.convertReport(at: report.path, toPDFAt: inside.path, error: &error),
       "exporting inside the report package must be refused")
expect((try Data(contentsOf: report)) == original, "a package-path refusal changed the report")

error = nil
expect(!PagesPDFConversion.convertReport(at: directory.appendingPathComponent("missing.pages").path,
                                         toPDFAt: pdf.path, error: &error),
       "a missing report must not convert")
expect(!FileManager.default.fileExists(atPath: pdf.path), "a missing report created a PDF")
expect((try Data(contentsOf: report)) == original, "a missing-report attempt changed another report")

if PagesApplication.url() == nil {
    error = nil
    expect(!PagesPDFConversion.convertReport(at: report.path, toPDFAt: pdf.path, error: &error),
           "with no Pages, conversion must fail")
    expect((try Data(contentsOf: report)) == original, "missing Pages deleted the report")
    expect(!FileManager.default.fileExists(atPath: pdf.path), "missing Pages left a PDF")
    expect(error?.localizedDescription.contains("Pages") == true,
           "the failure does not name Pages: \(error?.localizedDescription ?? "nil")")
}

let associated = PagesPDFConversion.associationAttributes(
    studyInstanceUID: "1.2.840.129.1",
    patientName: "VOLUME^GEOMETRY",
    patientID: "VOL-102",
    accessionNumber: "VOL102",
    studyDescription: "Pages PDF")
expect(associated["StudyInstanceUID"] == "1.2.840.129.1", "StudyInstanceUID is not carried")
expect(associated["PatientsName"] == "VOLUME^GEOMETRY", "patient name is not carried")
expect(associated["PatientID"] == "VOL-102", "patient ID is not carried")
expect(associated["AccessionNumber"] == "VOL102", "accession is not carried")
expect(associated["StudyDescription"] == "Pages PDF", "study description is not carried")
let empty = PagesPDFConversion.associationAttributes(
    studyInstanceUID: "", patientName: nil, patientID: nil,
    accessionNumber: nil, studyDescription: nil)
expect(empty["StudyInstanceUID"] == nil, "an empty UID must not be written onto the DICOM")

print("PASS: usable PDF, refused conversions preserve the report, association carries the study UID")
'''

with tempfile.TemporaryDirectory(prefix='horos-pages-pdf-') as tmp:
    folder = Path(tmp)
    (folder / 'main.swift').write_text(program)
    built = subprocess.run(
        ['xcrun', 'swiftc',
         str(root / 'Horos/Sources/PagesApplication.swift'),
         str(conversion),
         str(folder / 'main.swift'),
         '-o', str(folder / 'test')],
        capture_output=True, text=True)
    if built.returncode != 0:
        failures.append('PagesPDFConversion.swift did not compile:\n%s' % (built.stderr or built.stdout))
    else:
        ran = subprocess.run([str(folder / 'test'), str(folder)], capture_output=True, text=True)
        sys.stdout.write(ran.stdout)
        if ran.returncode != 0:
            failures.append(ran.stderr.strip() or ran.stdout.strip() or 'converter checks failed')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: Pages→PDF conversion refuses unsafe paths without touching the report, '
      'and the DICOM association carries the study UID')
