#!/usr/bin/env python3
"""A file the import refuses has to be named where someone can see it.

Both refusal paths used to reach the log only: the scan's own check, which drops
a file before it ever becomes an instance, and the one inside addFilesAtPaths:.
A study then arrived with images missing, or nothing arrived at all, and the
window said nothing - which is what "rejected with no visible error" means to
the person who sent the files.
"""
from pathlib import Path
import subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/DicomDatabase.h').read_bytes().decode('latin1')
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
failures = []

if 'lastImportRefusalSummary' not in header:
    failures.append('the database no longer publishes what the last import refused')
if 'addImportRefusalSummary: refusals.summary' not in database:
    failures.append('the refusals of addFilesAtPaths: no longer reach the window')
if 'is not a DICOM file this database can index", nil), lastPathComponent]]' not in database:
    failures.append("the scan's own refusal no longer reaches the window")
if '_database.lastImportRefusalSummary.length' not in browser:
    failures.append('the window no longer shows what the last import refused')
if 'LAST IMPORT: ' not in browser:
    failures.append('the line that names the refusal is gone')
# An idle scan must not wipe a refusal the person has not read yet.
if 'chunkIndex == 0 && chunkRange.length' not in database:
    failures.append('a scan with no files can clear the line again')
# And the description has to keep carrying the other two states.
for expected in ('IMPORT PAUSED', 'Local Database'):
    if expected not in browser:
        failures.append(f'the database description lost {expected!r}')

source = r'''
import Foundation
// The sentence the window shows comes from this type; it has to name files.
let refusals = ImportRefusals(considered: 3)
refusals.refuse("/tmp/one.dcm", reason: "is DICOM the parser could not read")
refusals.refuse("/tmp/two.dcm", reason: "is empty")
let summary = refusals.summary
precondition(summary.contains("2 of 3"), summary)
precondition(summary.contains("one.dcm") && summary.contains("two.dcm"), summary)
precondition(summary.contains("is empty"), summary)
// A folder of a thousand refusals must not print a thousand names.
let many = ImportRefusals(considered: 1000)
for index in 0..<1000 { many.refuse("/tmp/\(index).dcm", reason: "is empty") }
let long = many.summary
precondition(long.count < 600, "\(long.count) characters")
precondition(long.contains("and 992 more"), long)
precondition(ImportRefusals(considered: 5).summary.isEmpty)
print("PASS: the sentence names the files and their reasons, and stays short for a bad folder")
'''
with tempfile.TemporaryDirectory(prefix='horos-import-refusal-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(source)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/ImportRefusals.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    done = subprocess.run([str(p / 'test')], capture_output=True, text=True)
    if done.returncode:
        failures.append('the refusal sentence: ' + (done.stderr.strip() or done.stdout.strip()))
    else:
        print(done.stdout.strip())

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if failures else 0)
