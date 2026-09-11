#!/usr/bin/env python3
"""A list of identifiers exports the studies it names, and says what happened.

The request behind this is five hundred medical record numbers and no wish to
find each one by hand. Two things make that safe to run unattended, and both are
checked here: the list is resolved by identifier and never by name, so two
patients who share a name are never merged; and the run leaves a report - per
identifier, the studies found, the files, the bytes and a digest of them - so it
can be checked afterwards instead of trusted.

The digest is over the files, not over the order they were read: the same set
enumerated differently has to answer the same, and a file that changed, arrived
or went missing has to change it.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')

at = browser.find('- (NSString*) exportStudiesForIdentifiers:')
body = browser[at:browser.index('\n}', browser.index('[wait close]', at))] if at >= 0 else ''
if not body:
    failures.append('exportStudiesForIdentifiers:toDirectory:dryRun: is gone')
else:
    # By identifier. A predicate on the name is what merges two people.
    if 'patientID == %@' not in body:
        failures.append('the list is no longer resolved by patient identifier')
    if re.search(r'predicateWithFormat:\s*@"name\b', body):
        failures.append('the list is resolved by name, which merges patients who share one')
    # Cancellation, and a dry run that copies nothing.
    if '[wait aborted]' not in body or 'setCancel: YES' not in browser[at - 4000:at + 4000]:
        failures.append('the run cannot be cancelled')
    if 'if( dryRun) continue;' not in body:
        failures.append('a dry run would copy files')
    # The report, with the counts and the digest.
    for wanted in ('HorosFileSetDigest', 'rowForIdentifier:', 'horos-export-manifest.csv'):
        if wanted not in body:
            failures.append('the run does not produce %s' % wanted)
    if '@"not found"' not in body:
        failures.append('an identifier nothing answers to is not reported')

for failure in failures:
    print('FAIL: %s' % failure)
reported = len(failures)

with tempfile.TemporaryDirectory(prefix='horos-batch-export-') as tmp:
    p = Path(tmp)
    # Files whose digests are known independently, so the Swift answer can be
    # checked against one computed here rather than against itself.
    contents = [b'first', b'second', b'third']
    paths = []
    for index, data in enumerate(contents):
        path = p / ('file-%d.bin' % index)
        path.write_bytes(data)
        paths.append(str(path))
    expected = hashlib.sha256()
    for digest in sorted(hashlib.sha256(data).hexdigest() for data in contents):
        expected.update(digest.encode())

    main = '''import Foundation

let paths = %s
let digest = FileSetDigest()
for path in paths { precondition(digest.add(path: path), path) }
precondition(digest.fileCount == 3)
precondition(digest.byteCount == %d)
precondition(digest.unreadable.isEmpty)
print("digest", digest.hexDigest)

// The same files in another order answer the same.
let reversed = FileSetDigest()
for path in paths.reversed() { reversed.add(path: path) }
precondition(reversed.hexDigest == digest.hexDigest, "the order of reading changed the answer")

// One file fewer does not.
let fewer = FileSetDigest()
for path in paths.dropLast() { fewer.add(path: path) }
precondition(fewer.hexDigest != digest.hexDigest)
precondition(FileSetDigest().hexDigest == "", "nothing hashed is not a digest of nothing")

// A file that cannot be read is named rather than passed over in silence.
let missing = FileSetDigest()
precondition(!missing.add(path: paths[0] + "-not-here"))
precondition(missing.unreadable.count == 1 && missing.fileCount == 0)

// The list: one per line, comments and blanks dropped, each kept once, and a
// spreadsheet column taken as its first field.
let identifiers = BatchExportManifest.identifiers(fromText: """
MRN-1
  MRN-2  # the second

MRN-1
# a whole line
"MRN-3",Silva Maria,2026
""")
precondition(identifiers == ["MRN-1", "MRN-2", "MRN-3"], "\\(identifiers)")
precondition(BatchExportManifest.identifiers(fromText: "").isEmpty)

// A row says all of it, in the order the header promises.
let row = BatchExportManifest.row(identifier: "MRN-1", status: "exported", names: ["A", "B"],
                                  studies: 2, files: 5, bytes: 1234, digest: "abc", detail: "")
precondition(row.count == BatchExportManifest.header.count)
precondition(row[0] == "MRN-1" && row[1] == "exported" && row[2] == "A; B")
precondition(row[3] == "2" && row[4] == "5" && row[5] == "1234" && row[6] == "abc")

print("PASS: the digest is over the files, not their order, and the list is read once each")
''' % (json.dumps(paths), sum(len(data) for data in contents))

    (p / 'main.swift').write_text(main)
    build = subprocess.run(['swiftc', str(root / 'Horos/Sources/BatchExportManifest.swift'),
                            str(p / 'main.swift'), '-o', str(p / 'test')],
                           capture_output=True, text=True)
    if build.returncode:
        print(build.stderr.strip()[-2000:])
        sys.exit('the manifest did not compile')
    checks = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    print((checks.stdout + checks.stderr).strip())
    if checks.returncode:
        failures.append('the manifest does not hold together')
    else:
        answered = re.search(r'digest ([0-9a-f]{64})', checks.stdout)
        if not answered:
            failures.append('the digest was not reported')
        elif answered.group(1) != expected.hexdigest():
            failures.append('the digest is %s where SHA-256 over the sorted file digests is %s'
                            % (answered.group(1), expected.hexdigest()))

for failure in failures[reported:]:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: identifiers resolve one by one, and the report can be checked against the files')
