#!/usr/bin/env python3
"""An archive handed to the importer ends with a statement of what it held.

Measured before the change on the development build, three archives dropped into
the incoming folder of a running Horos:

  - `no-dicom.zip` and `mixed.zip` left the incoming folder and were never
    mentioned again;
  - `corrupt.zip` stayed in the decompression folder for ever - nothing rescans
    that folder, so the file was neither imported nor reported.

The same run exposed why the earlier archive measurements looked like nothing at
all happened: `Decompress`, the helper that expands archives, was signed with the
hardened runtime and no entitlements, so it could not load the ad-hoc frameworks
beside it and died in dyld before running. That is checked here too, because
without it the whole path is untestable.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

ledger_source = root / 'Horos/Sources/ArchiveImportLedger.swift'
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
decompress = (root / 'Decompress/Decompress.mm').read_bytes().decode('latin1')
launcher = (root / 'script/build_and_run.sh').read_text()

DRIVER = '''
func emit(_ key: String, _ value: String) { print("\\(key)\\t\\(value)") }
let ledger = ArchiveImportLedger.shared

emit("entry", ArchiveImportLedger.archiveComponent(ofRelativePath: "a.zip/x.dcm") ?? "nil")
emit("deep", ArchiveImportLedger.archiveComponent(ofRelativePath: "a.OSIRIXZIP/sub/x.dcm") ?? "nil")
emit("archive-itself", ArchiveImportLedger.archiveComponent(ofRelativePath: "a.zip") ?? "nil")
emit("plain-folder", ArchiveImportLedger.archiveComponent(ofRelativePath: "folder/x.dcm") ?? "nil")

// An archive that expanded to nothing still gets a line.
emit("empty", ledger.verdictForArchive("/in/empty.zip", keptDirectoryName: "NOT READABLE"))

// The case the issue is about: it expanded, and none of it was DICOM.
for _ in 0..<3 { ledger.recordKeptEntry(inArchive: "/in/no-dicom.zip") }
emit("no-dicom", ledger.verdictForArchive("/in/no-dicom.zip", keptDirectoryName: "NOT READABLE"))

// Mixed, with the deleting preference on for one of them.
ledger.recordIndexedEntry(inArchive: "/in/mixed.zip")
ledger.recordIndexedEntry(inArchive: "/in/mixed.zip")
ledger.recordKeptEntry(inArchive: "/in/mixed.zip")
ledger.recordDeletedEntry(inArchive: "/in/mixed.zip")
emit("mixed", ledger.verdictForArchive("/in/mixed.zip", keptDirectoryName: "NOT READABLE"))

// A DICOM sent for transcoding is still a DICOM entry of the archive, and an
// archive within the archive is counted but reported on its own.
ledger.recordQueuedEntry(inArchive: "/in/nested.zip")
ledger.recordNestedArchive(inArchive: "/in/nested.zip")
emit("nested", ledger.verdictForArchive("/in/nested.zip", keptDirectoryName: "NOT READABLE"))

// Reporting consumes the tally: the expansion is gone and nothing can be added.
emit("consumed", ledger.hasArchive("/in/mixed.zip") ? "yes" : "no")
'''

# --- what the archive's closing line says -------------------------------------
results = {}
if not ledger_source.exists():
    failures.append('there is no archive ledger, so no archive can be summed up')
else:
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-archive-') as directory:
            # Top-level statements are only allowed in a file called main.swift.
            (Path(directory) / 'main.swift').write_text(DRIVER)
            binary = Path(directory) / 'ledger'
            built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                    str(ledger_source), str(Path(directory) / 'main.swift')],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the archive ledger does not compile:\n%s' % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the driver failed: %s' % run.stderr[-800:])
                for line in run.stdout.splitlines():
                    key, _, value = line.partition('\t')
                    results[key] = value

if results:
    expected = {
        'entry': 'a.zip',
        'deep': 'a.OSIRIXZIP',
        # An archive is not an entry of itself, and an ordinary folder is not one.
        'archive-itself': 'nil',
        'plain-folder': 'nil',
        'empty': 'empty.zip: no entries',
        'no-dicom': 'no-dicom.zip: 3 entries, no DICOM; 3 kept in NOT READABLE',
        'mixed': 'mixed.zip: 4 entries, 2 DICOM; 1 kept in NOT READABLE, 1 deleted',
        'nested': 'nested.zip: 2 entries, 1 DICOM; 1 nested archive expanded separately',
        'consumed': 'no',
    }
    for key, want in expected.items():
        got = results.get(key)
        if got != want:
            failures.append('%s: %r, expected %r' % (key, got, want))

# --- the incoming scan has to feed it and then say it -------------------------
if 'HorosArchiveImportLedger' not in database:
    failures.append('the incoming scan never records anything about an archive')
else:
    if 'archiveComponentOfRelativePath' not in database:
        failures.append('the scan does not work out which archive an entry came from')
    at = database.find('BOOL dirContainsStuff')
    window = database[at:at + 1400] if at >= 0 else ''
    if 'verdictForArchive' not in window:
        failures.append('an expansion that has run out is deleted without the archive being '
                        'summed up: that is the only moment at which anything still knows')
    if 'isArchiveName' not in window:
        failures.append('every emptied folder would be reported as an archive')
    for recorder in ('recordIndexedEntryInArchive', 'recordKeptEntryInArchive',
                     'recordDeletedEntryInArchive', 'recordNestedArchiveInArchive',
                     'recordQueuedEntryInArchive'):
        if recorder not in database:
            failures.append('%s is never called, so that outcome is missing from the count'
                            % recorder)

    # A multipart response is split into separate files and deleted; carrying on
    # would test a path that no longer exists and call it unreadable.
    at = database.find('if (dicomFileCreated)')
    window = database[at:at + 600] if at >= 0 else ''
    if 'continue;' not in window:
        failures.append('a split multipart response falls through to the readability test on a '
                        'file that has just been deleted')

# --- an archive that cannot be expanded is handed back, not stranded ----------
if 'surrenderUnreadableArchive' not in decompress:
    failures.append('an archive that cannot be expanded still stays in the decompression folder, '
                    'which nothing ever rescans')
else:
    if decompress.count('HorosArchiveExtraction outcome = extractDICOMArchive') != 2:
        failures.append('only one of the two archive call sites reports what happened')
    if 'HorosArchiveExpandedNotCleared' not in decompress:
        failures.append('an archive whose contents are already in place would be handed back and '
                        'imported twice')
    # An archive that could not be expanded because the destination was full or
    # unwritable is not a bad archive. Disposing of it there destroys something
    # the next attempt could read perfectly well.
    if 'HorosArchiveNotExpandedForNow' not in decompress:
        failures.append('a destination that is full or unwritable is treated as a bad archive, '
                        'so the archive is disposed of instead of being tried again')
    if 'returnArchiveForRetry' not in decompress:
        failures.append('nothing puts such an archive back for another attempt')
    if 'status == 50' not in decompress:
        failures.append("unzip's disk-full status is not told apart from an archive that is at "
                        'fault')
    if 'status != 0 && status != 1' not in decompress:
        failures.append('unzip exit 1 is a warning with the contents extracted; treating it as a '
                        'failure throws away everything that came out')
    at = decompress.find('static BOOL surrenderUnreadableArchive')
    window = decompress[at:at + 1200]
    if 'horos-unexpanded' not in window:
        failures.append('the archive is handed back under a name that still reads as an archive, '
                        'so it is sent straight back to the decompression folder')
    if 'could not be expanded as an archive' not in database:
        failures.append("the application's own log never says the file it is disposing of was an "
                        'archive it failed to expand: that reason is only in the helper\'s stderr, '
                        'which the application does not capture')
    if 'unzip exited with' not in decompress:
        failures.append('nothing says why the archive could not be expanded')

# --- and the helper that expands them has to be able to run -------------------
if '--options runtime' in launcher and '--entitlements "$entitlements"' not in launcher:
    failures.append('the development bundle signs the helpers in Resources with the hardened '
                    'runtime and no entitlements: library validation then stops Decompress from '
                    'loading the frameworks beside it, and every archive silently does nothing')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: an archive says how many entries it held, how many were DICOM and where the rest '
      'went, and one that cannot be expanded is handed back for the same verdict instead of '
      'being left in a folder nothing reads')
