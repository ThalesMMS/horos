#!/usr/bin/env python3
"""RTF and RTFD reports become readable PDFs, and a failure is one (#649).

`+[DicomStudy(Report) transformReportAtPath:toPdfAtPath:]` converted RTF reports
with /System/Library/Printers/Libraries/convert, gone since OS X 10.8, or else
cupsfilter, which has no filter from text/rtf to application/pdf on macOS 27: it
exited 1 over the empty PDF the app had just created, and that empty PDF was what
every caller used - the PDF export, the DICOM PDF, the web portal, a medium.

`HorosRichTextReportPDF` draws the report instead. Compiled here and run over
files this test writes:

* an RTF of several pages: the PDF is readable, its pages carry the report's text
  in order, and its page size is the document's;
* an RTFD with an image: one page, the text, and an image drawn on it;
* an empty report: one empty page, still a readable PDF;
* a file that is not RTF: an error, no PDF and no leftovers beside it;
* a destination that already holds a PDF: replaced by this report's.

The source is checked too: the two external tools are gone, the RTF branch raises
what the converter says, a PDF that is missing or empty is a failure for every
caller, and each caller says so instead of going on with it.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

report = (root / 'Horos/Sources/DicomStudy+Report.mm').read_text()
transform = report[report.index('+(void)transformReportAtPath:(NSString*)reportPath toPdfAtPath:(NSString*)outPdfPath'):]
transform = transform[:transform.index('\n-(void)saveReportAsPdfAtPath:')]
for gone in ('N2Shell execute:@"/System/Library/Printers/Libraries/convert"', 'setLaunchPath: @"/usr/sbin/cupsfilter"',
             'fileExistsAtPath: @"/usr/sbin/cupsfilter"'):
    if gone in report:
        failures.append(f'a report is still converted with {gone}')
if 'HorosRichTextReportPDF convertReportAtPath:reportPath toPDFAtPath:outPdfPath error:&error' not in transform:
    failures.append('the RTF branch does not draw the report')
if 'isUsablePDFAtPath:outPdfPath' not in transform or transform.index('isUsablePDFAtPath:outPdfPath') < transform.index('HorosRichTextReportPDF'):
    failures.append('a missing or empty PDF is not a failure after the conversion')
if 'NSRunAlertPanel' in report:
    failures.append('a conversion failure still opens a modal panel from inside the conversion')

browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
export = browser[browser.index('- (IBAction) convertReportToPDF: (id)sender'):]
export = export[:export.index('- (IBAction)deleteReport:')]
if 'NSRunAlertPanel' not in export:
    failures.append('Convert Report to PDF does not tell the user when nothing was written')
batch = browser[browser.index('- (IBAction) convertReportToDICOMSR: (id)sender'):]
batch = batch[:batch.index('- (IBAction) convertReportToPDF:')]
if 'failedReports' not in batch or 'NSRunAlertPanel' not in batch:
    failures.append('the DICOM PDF batch does not tell the user which reports failed')
study = (root / 'Horos/Sources/DicomStudy.m').read_bytes().decode('latin1')
if 'notificationTitle: NSLocalizedString(@"Report Error", nil)' not in study:
    failures.append('a validated study whose DICOM PDF failed says nothing')
burner = (root / 'Horos/Sources/BurnerWindowController.m').read_bytes().decode('latin1')
if 'report not converted to PDF for the medium' not in burner:
    failures.append('the medium does not fall back to the report as it is')

driver = r'''
import AppKit
import PDFKit

var failed = false
func expect(_ condition: Bool, _ message: String) {
    if !condition { print("FAIL: \(message)"); failed = true }
}
let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
func words(_ text: String) -> [String] {
    text.components(separatedBy: CharacterSet.whitespacesAndNewlines).filter { !$0.isEmpty && $0 != "\u{fffc}" }
}
// The text through PDFKit's parser, the way anything reading the report back would.
func pdfText(_ url: URL) -> String {
    guard let document = PDFDocument(url: url) else { return "" }
    return (0..<document.pageCount).compactMap { document.page(at: $0)?.string }.joined(separator: "\n")
}

// A report of several pages, with accents and a paper size of its own.
let paragraph = NSMutableParagraphStyle()
paragraph.paragraphSpacing = 6
let body = NSMutableAttributedString()
body.append(NSAttributedString(string: "Relatório sintético — paciente ÜNÏCODE\n",
                               attributes: [.font: NSFont.boldSystemFont(ofSize: 18), .paragraphStyle: paragraph]))
for line in 1...90 {
    body.append(NSAttributedString(string: "Linha \(line) do relatório com achados e medidas.\n",
                                   attributes: [.font: NSFont.systemFont(ofSize: 12), .paragraphStyle: paragraph]))
}
let paper = NSSize(width: 595, height: 842)
let documentAttributes: [NSAttributedString.DocumentAttributeKey: Any] = [
    .documentType: NSAttributedString.DocumentType.rtf, .paperSize: NSValue(size: paper),
    .leftMargin: 72, .rightMargin: 72, .topMargin: 72, .bottomMargin: 72]
let rtf = directory.appendingPathComponent("report.rtf")
try body.data(from: NSRange(location: 0, length: body.length), documentAttributes: documentAttributes).write(to: rtf)
let pdf = directory.appendingPathComponent("report.pdf")
do {
    try RichTextReportPDF.convert(reportPath: rtf.path, toPDFAtPath: pdf.path)
} catch {
    expect(false, "the RTF report was refused: \(error.localizedDescription)")
}
if let document = CGPDFDocument(pdf as CFURL) {
    expect(document.numberOfPages > 1, "a 91-line report takes more than a page: \(document.numberOfPages)")
    let box = document.page(at: 1)!.getBoxRect(.mediaBox)
    expect(abs(box.width - paper.width) < 1 && abs(box.height - paper.height) < 1, "the page is the document's paper: \(box)")
    let read = words(pdfText(pdf))
    let written = words(body.string)
    expect(read == written, "the PDF reads back the report's text (\(read.count) of \(written.count) words, first difference "
           + "\(zip(read, written).first(where: { $0 != $1 }).map { "\($0) / \($1)" } ?? "none"))")
} else {
    expect(false, "the PDF is not readable")
}

// An RTFD with an image.
let image = NSImage(size: NSSize(width: 120, height: 60))
image.lockFocus()
NSColor.systemBlue.setFill()
NSRect(x: 0, y: 0, width: 120, height: 60).fill()
image.unlockFocus()
let attachment = NSTextAttachment()
attachment.image = image
let rich = NSMutableAttributedString(string: "Imagem do relatório:\n", attributes: [.font: NSFont.systemFont(ofSize: 12)])
rich.append(NSAttributedString(attachment: attachment))
rich.append(NSAttributedString(string: "\nFim do relatório.\n", attributes: [.font: NSFont.systemFont(ofSize: 12)]))
let rtfd = directory.appendingPathComponent("report.rtfd")
let wrapper = rich.rtfdFileWrapper(from: NSRange(location: 0, length: rich.length),
                                   documentAttributes: [.documentType: NSAttributedString.DocumentType.rtfd])!
try wrapper.write(to: rtfd, options: .atomic, originalContentsURL: nil)
let richPDF = directory.appendingPathComponent("rich.pdf")
do {
    try RichTextReportPDF.convert(reportPath: rtfd.path, toPDFAtPath: richPDF.path)
} catch {
    expect(false, "the RTFD report was refused: \(error.localizedDescription)")
}
if let document = CGPDFDocument(richPDF as CFURL), let page = document.page(at: 1) {
    expect(document.numberOfPages == 1, "the RTFD is one page: \(document.numberOfPages)")
    expect(words(pdfText(richPDF)) == words(rich.string), "the RTFD text is in the PDF: \(pdfText(richPDF))")
    var resources: CGPDFDictionaryRef?
    var xobjects: CGPDFDictionaryRef?
    let hasImage = CGPDFDictionaryGetDictionary(page.dictionary!, "Resources", &resources)
        && CGPDFDictionaryGetDictionary(resources!, "XObject", &xobjects)
        && CGPDFDictionaryGetCount(xobjects!) > 0
    expect(hasImage, "the attached image is drawn on the page")
} else {
    expect(false, "the RTFD PDF is not readable")
}

// An empty report is still a PDF.
let empty = directory.appendingPathComponent("empty.rtf")
try NSAttributedString(string: "").data(from: NSRange(location: 0, length: 0),
                                        documentAttributes: [.documentType: NSAttributedString.DocumentType.rtf]).write(to: empty)
let emptyPDF = directory.appendingPathComponent("empty.pdf")
do {
    try RichTextReportPDF.convert(reportPath: empty.path, toPDFAtPath: emptyPDF.path)
    expect(CGPDFDocument(emptyPDF as CFURL)?.numberOfPages == 1, "an empty report is one empty page")
} catch {
    expect(false, "an empty report was refused: \(error.localizedDescription)")
}

// Not a report at all: an error, nothing written, nothing left behind.
let broken = directory.appendingPathComponent("broken.rtf")
try Data([0x00, 0x01, 0x02, 0xff, 0xfe]).write(to: broken)
let brokenPDF = directory.appendingPathComponent("broken.pdf")
do {
    try RichTextReportPDF.convert(reportPath: broken.path, toPDFAtPath: brokenPDF.path)
    expect(false, "a file that is not RTF was converted")
} catch {
    expect(!error.localizedDescription.isEmpty, "the refusal says why")
}
expect(!FileManager.default.fileExists(atPath: brokenPDF.path), "a refused conversion writes no PDF")
let leftovers = (try? FileManager.default.contentsOfDirectory(atPath: directory.path))?.filter { $0.hasPrefix(".horos-report-") } ?? []
expect(leftovers.isEmpty, "no half-written PDF is left: \(leftovers)")

// A destination that already holds a PDF is replaced.
let existing = directory.appendingPathComponent("existing.pdf")
try Data("not a pdf at all".utf8).write(to: existing)
do {
    try RichTextReportPDF.convert(reportPath: rtf.path, toPDFAtPath: existing.path)
    expect(CGPDFDocument(existing as CFURL) != nil, "the destination holds this report's PDF")
} catch {
    expect(false, "replacing a destination failed: \(error.localizedDescription)")
}
print(failed ? "FAILED" : "ok")
exit(failed ? 1 : 0)
'''

if not failures:
    with tempfile.TemporaryDirectory(prefix='horos-report-pdf-') as temporary:
        work = Path(temporary)
        (work / 'main.swift').write_text(driver)
        binary = work / 'reportpdf'
        built = subprocess.run(['xcrun', 'swiftc', '-module-name', 'ReportPDF', '-framework', 'PDFKit',
                                str(root / 'Horos/Sources/RichTextReportPDF.swift'), str(work / 'main.swift'), '-o', str(binary)],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('RichTextReportPDF.swift does not build: ' + built.stderr[-2000:])
        else:
            data = work / 'reports'
            data.mkdir()
            run = subprocess.run([str(binary), str(data)], capture_output=True, text=True, timeout=120)
            if run.returncode != 0:
                failures.append((run.stdout + run.stderr).strip())

if failures:
    print('\n'.join(f if f.startswith('FAIL') else 'FAIL: ' + f for f in failures))
    raise SystemExit(1)
print('reports: RTF and RTFD drawn into readable PDFs, a refusal leaves none, every caller treats it as a failure')
