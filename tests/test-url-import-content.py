#!/usr/bin/env python3
"""What a URL answers with decides where it goes, not the extension it lacks.

`-[BrowserController addURLToDatabaseFiles:]` wrote whatever came back into the
database's own file folder as a `.dcm`, and reported success as long as some
bytes had arrived. Measured against `tools/serve-url-import-fixture.py`, whose
paths carry no extension at all:

    4.dcm          76  HTML document text
    3.dcm        2978  Zip archive data
    2.dcm        1360  DICOM medical imaging data

Three files in the folder the database keeps its images in; one study, one image.
The zip was expanded by nothing and indexed by nothing, the sign-in page a proxy
answered with was a 76-byte "DICOM", and both were reported as downloads that
worked.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
report = root / 'Horos/Sources/URLImportReport.swift'
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
scripting = (root / 'Horos/Sources/Scripting_Additions.m').read_bytes().decode('latin1')

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

var dicom = Data(repeating: 0, count: 128)
dicom.append(Data("DICM".utf8))
dicom.append(Data(repeating: 7, count: 64))
emit("dicom", URLImportReport.fileExtension(forPayload: dicom))

let zip = Data([0x50, 0x4B, 0x03, 0x04]) + Data(repeating: 0, count: 200)
emit("zip", URLImportReport.fileExtension(forPayload: zip))

emit("html", URLImportReport.fileExtension(forPayload: Data("<html><body>Sign in</body></html>".utf8)))
emit("empty", URLImportReport.fileExtension(forPayload: Data()))
// A truncated object that has not reached the magic is not a DICOM object.
emit("short", URLImportReport.fileExtension(forPayload: Data(repeating: 0, count: 100)))

let outcome = URLImportReport()
outcome.recordIndexed(url: "http://127.0.0.1:11198/instance")
outcome.recordExpanded(url: "http://127.0.0.1:11198/archive")
emit("clean", outcome.everythingArrived ? "yes" : "no")
outcome.recordRefused(url: "http://127.0.0.1:11198/page", reason: "76 bytes that are neither")
outcome.recordFailed(url: "http://127.0.0.1:11198/missing", reason: "could not be opened")
emit("dirty", outcome.everythingArrived ? "yes" : "no")
emit("summary", outcome.summary.replacingOccurrences(of: "\\n", with: " | "))
'''

results = {}
if not report.exists():
    failures.append('there is no report of what a URL answered with')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-url-') as directory:
            # Top-level statements are only allowed in a file called main.swift.
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'urlimport'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(report), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the report does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    expected = {
        'dicom': 'dcm', 'zip': 'zip',
        # Neither of these may be disguised as an image.
        'html': '', 'empty': '', 'short': '',
        'clean': 'yes', 'dirty': 'no',
        'summary': ('1 added to the database | 1 handed to the import folder to be expanded | '
                    '127.0.0.1/missing could not be downloaded: could not be opened | '
                    '127.0.0.1/page is not something this database can take: 76 bytes that are neither'),
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))

# --- the download has to route by content ------------------------------------
at = browser.find('- (NSArray*)downloadURLs:', browser.find('@implementation BrowserController'))
window = browser[at:at + 4200] if at >= 0 else ''
if not window:
    failures.append('there is no download that reports what it did')
else:
    if 'fileExtensionForPayload' not in window:
        failures.append('the content is not looked at, so a zip and a sign-in page are still '
                        'written into the database folder as DICOM objects')
    if 'incomingDirPath' not in window:
        failures.append('anything that is not a DICOM object is still written straight into the '
                        "database's file folder, where nothing will ever look at it")
    if 'uniquePathForNewDataFileWithExtension' not in window:
        failures.append('a DICOM object no longer goes into the database directly')
    if 'initiateImportFilesFromIncomingDirUnlessAlreadyImporting' not in window:
        failures.append('nothing asks the importer to look at what was handed to it')
    if 'recordFailedURL' not in window:
        failures.append('a download that failed is not reported')

# --- and the sheet has to say what happened ----------------------------------
at = browser.find('- (void)addURLToDatabaseEnd: (id)sender')
window = browser[at:at + 1200] if at >= 0 else ''
if window and 'report' not in window:
    failures.append('the URL sheet still says only "I\'m not able to download this file"')

# --- the AppleScript command must not raise out of the handler ---------------
at = scripting.find('if( [command isEqualToString:@"DownloadURLFile"])')
window = scripting[at:at + 1400] if at >= 0 else ''
if not window:
    failures.append('the DownloadURLFile command is gone')
else:
    if 'valueForKey:@"completePath"' in window:
        failures.append('the command still asks an NSString for a completePath, which raises out '
                        'of the AppleEvent handler')
    if 'files.count == 0' not in window:
        failures.append('the command still indexes the first result without checking there is one')
    if 'setScriptErrorString' not in window:
        failures.append('a script is told the command failed without being told why')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a URL that answers with an archive is expanded, one that answers with a page is named '
      'and refused, and a DICOM object still goes straight into the database')
