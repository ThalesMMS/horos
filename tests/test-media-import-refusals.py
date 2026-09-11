#!/usr/bin/env python3
"""A file an import cannot read is named, and a damaged disc does not hang.

`-[DicomDatabase addFilesAtPaths:…]` builds a dictionary for every path it is
given and drops the ones it cannot. The drop was silent unless the file was
already inside the database folder:

    if (curFile) { ... if (curDict) { add } else { /* only if in dataDirPath */ } }

Measured on a disc with six good CT instances and five broken ones - a truncated
file, an empty one, a text file wearing a .dcm name, a DICOM whose transfer
syntax does not exist, and a link to nothing:

    HOROSCD: 16 file(s) on the medium, 6 named by the index, 1 more found by
             reading it, 7 instance(s) to take
    not able to load the image : /Volumes/HOROSCD/BROKEN/truncated.dcm
    studies 1  series 3  images 7

The import did not hang - it took 241 ms - and said nothing at all about the four
files it refused. The truncated one parsed far enough to be indexed and failed
later, when its thumbnail was wanted.

Four of the five never reached `addFilesAtPaths:` at all: the scan filters with
`[DicomFile isDICOMFile:]` first, so that is where a damaged medium loses its
files. Both places record now, and `HorosImportRefusals` looks at each refused
file and says why.

The application does not stop either. An AppleEvent is delivered to the main run
loop, so a reply to one is proof the main thread ran - an XML-RPC call is not,
because `N2XMLRPCConnection` answers on the connection's own thread. Asked every
200 ms through an import of 1200 instances, the main thread answered 221 times
with a worst reply of 73 ms, and 219 times at 81 ms with the disc pulled out one
second in. The other half of
the issue is that a slow medium stays cancellable, which is checked in source
here: every loop that touches a file on the medium asks whether the thread was
cancelled, and moves the progress the panel shows.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
refusals = root / 'Horos/Sources/ImportRefusals.swift'
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
scan = (root / 'Horos/Sources/DicomDatabase+Scan.mm').read_bytes().decode('latin1')

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }

let directory = URL(fileURLWithPath: NSTemporaryDirectory())
    .appendingPathComponent("horos-refusals-\\(getpid())")
try! FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: directory) }

func write(_ name: String, _ bytes: [UInt8]) -> String {
    let url = directory.appendingPathComponent(name)
    try! Data(bytes).write(to: url)
    return url.path
}

let empty = write("empty.dcm", [])
var dicom = [UInt8](repeating: 0, count: 128)
dicom.append(contentsOf: Array("DICM".utf8))
dicom.append(contentsOf: Array("rubbish".utf8))
let unparseable = write("unknown-syntax.dcm", dicom)
let text = write("notes.dcm", Array("This is not a DICOM file.\\n".utf8))
let link = directory.appendingPathComponent("dangling.dcm")
try! FileManager.default.createSymbolicLink(at: link, withDestinationURL:
    directory.appendingPathComponent("nowhere.dcm"))
let gone = directory.appendingPathComponent("never-existed.dcm").path

emit("empty", ImportRefusals.reason(for: empty))
emit("unparseable", ImportRefusals.reason(for: unparseable))
emit("text", ImportRefusals.reason(for: text))
emit("link", ImportRefusals.reason(for: link.path))
emit("gone", ImportRefusals.reason(for: gone))

// Nothing refused says nothing.
emit("quiet", ImportRefusals(considered: 11).summary)

let some = ImportRefusals(considered: 11)
some.refuse(empty)
some.refuse(text)
some.refuse(link.path)
emit("count", String(some.count))
emit("some", some.summary)

// More than the report will name: the names stop and the kinds are counted.
let many = ImportRefusals(considered: 40)
for _ in 0..<7 { many.refuse(empty) }
for _ in 0..<5 { many.refuse(text) }
emit("many", many.summary)

// One file considered, one refused.
let single = ImportRefusals(considered: 1)
single.refuse(empty)
emit("single", single.summary)
'''

results = {}
if not refusals.exists():
    failures.append('nothing says which files an import could not read')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-refusals-') as directory:
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'refusals'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(refusals), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the refusal report does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    expected = {
        'empty': 'is empty',
        'unparseable': 'is DICOM the parser could not read',
        'text': 'was not recognised as DICOM',
        'link': 'is a link to nothing',
        'gone': 'is no longer there',
        'quiet': '',
        'count': '3',
        'some': '3 of 11 files could not be indexed: empty.dcm is empty, '
                'notes.dcm was not recognised as DICOM, dangling.dcm is a link to nothing',
        'many': '12 of 40 files could not be indexed: empty.dcm is empty, empty.dcm is empty, '
                'empty.dcm is empty, empty.dcm is empty, empty.dcm is empty, empty.dcm is empty, '
                'empty.dcm is empty, notes.dcm was not recognised as DICOM, and 4 more '
                '(7 is empty, 5 was not recognised as DICOM)',
        'single': '1 of 1 file could not be indexed: empty.dcm is empty',
    }
    for key, want in expected.items():
        if results.get(key) != want:
            failures.append('%s: expected %r, got %r' % (key, want, results.get(key)))

# --- the import uses it -------------------------------------------------------
start = database.find('-(NSArray*)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)'
                      'postNotifications dicomOnly:(BOOL)dicomOnly rereadExistingItems:'
                      '(BOOL)rereadExistingItems generatedByOsiriX:(BOOL)generatedByOsiriX '
                      'importedFiles: (BOOL) importedFiles returnArray: (BOOL) returnArray\n{')
if start < 0:
    failures.append('-addFilesAtPaths:... is gone')
else:
    region = re.sub(r'//[^\n]*', '', database[start:database.find('\n-(NSArray*)', start + 10)])
    if 'HorosImportRefusals' not in region:
        failures.append('the import does not record what it could not read')
    if region.count('[refusals refuse: newFile]') < 2:
        failures.append('a file is refused on only one of the two ways it can fail: a file that '
                        'could not be opened at all, and one that opened and could not be indexed')
    if 'refusals.summary' not in region:
        failures.append('what could not be read is never said')
    at = region.find('refusals.summary')
    if at > 0 and 'if (refusals.count)' not in region[at - 120:at]:
        failures.append('an import that refused nothing still logs a line')

# --- the scan uses it too, which is where a damaged medium loses its files ----
code = re.sub(r'//[^\n]*', '', scan)
if 'HorosImportRefusals' not in code:
    failures.append('a file the scan itself would not take is dropped without a word, and that is '
                    'where a damaged medium loses its files: isDICOMFile: says no and they never '
                    'reach addFilesAtPaths:')
else:
    if '[refusals refuse: path]' not in code:
        failures.append('the scan records nothing')
    if 'refusals.considered = examined' not in code:
        failures.append('the scan counts its refusals against the wrong total')
    at = code.find('refusals.summary')
    if at < 0:
        failures.append('the scan never says what it would not take')
    elif 'if (refusals.count)' not in code[at - 120:at]:
        failures.append('a medium with nothing wrong with it still logs a line')

# --- and a slow medium stays cancellable, with progress to show --------------
at = code.find('for (NSInteger i = 0; i < allpaths.count; ++i)')
if at < 0:
    failures.append('the loop that reads the medium is gone')
else:
    window = code[at:code.find('[timing end: @"reading"', at)]
    if 'thread.isCancelled' not in window:
        failures.append('reading the medium cannot be cancelled')
    if 'thread.progress' not in window:
        failures.append('reading the medium shows no progress')

wait = code.find('copyFilesThread.isFinished == NO')
if wait < 0:
    failures.append('the wait for the copy is gone')
else:
    window = code[wait:code.find('thread.supportsCancel = NO', wait)]
    if 'thread.isCancelled' not in window or '[copyFilesThread cancel]' not in window:
        failures.append('a copy from a slow medium cannot be cancelled while it runs')
    if 'thread.progress = copyFilesThread.progress' not in window:
        failures.append('the copy\'s progress is not passed on, so a slow copy looks stalled')

adding = re.sub(r'//[^\n]*', '', database)
if 'if (thread.isCancelled)\n            {\n                [dicomFilesArray removeAllObjects];' not in adding:
    failures.append('indexing a medium cannot be cancelled part way')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: every file an import could not read is named with the reason, and each loop over a '
      'slow medium reports progress and can be cancelled')
