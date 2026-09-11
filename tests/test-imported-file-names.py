#!/usr/bin/env python3
"""A file that is not DICOM keeps the name it arrived with, long enough to be read.

A raster file has no identity but its name: `-[DicomFile getImageFile]` makes the
study, the series and the instance out of it, and a trailing number is what turns
`scan001.jpg`, `scan002.jpg`, ... into one series. The database copies the file
into its own numbered layout first - `2173.tif` - and the reader then saw that
number: stripping four digits from `2173` leaves nothing, so every raster file
came out with the same empty stem and they all fell into a single series, which
also took one of their extensions as its modality.

The database now leaves the original name where the reader can take it.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
if 'HorosImportedFileNames rememberName: lastPathComponent forPath: dstPath' not in database:
    failures.append('the name a non-DICOM file arrived with is not kept')
if 'if (isDicomFile == NO)\n' not in database:
    failures.append('the name is kept for DICOM files too, which do not need it')

reader = (root / 'Horos/Sources/DicomFile.mm').read_bytes().decode('latin1')
block = reader[reader.index('-(short) getImageFile'):]
block = block[:block.index('fileType = [@"IMAGE" retain];')]
if 'HorosImportedFileNames nameForPath: filePath' not in block:
    failures.append('the reader does not ask for the name the file arrived with')
if '[filePath lastPathComponent]' in block.replace(
        'importedName = [filePath lastPathComponent];', ''):
    failures.append('the identity is still made out of the stored name somewhere')
for what in ('studyID = [[NSString alloc] initWithString:importedName]',
             'self.serieID = importedName',
             'name = [[NSString alloc] initWithString:importedName]',
             'study = [[NSString alloc] initWithString:importedName]'):
    if what not in block:
        failures.append('%s is not taken from the name it arrived with' % what.split(' =')[0])

source = r'''
import Foundation

// One name, taken once: a stored file is read on the way in and not again.
ImportedFileNames.forgetAll()
ImportedFileNames.remember("scan001.jpg", forPath: "/db/10000/2173.jpg")
precondition(ImportedFileNames.count == 1)
precondition(ImportedFileNames.name(forPath: "/db/10000/2173.jpg") == "scan001.jpg")
precondition(ImportedFileNames.name(forPath: "/db/10000/2173.jpg") == nil, "it was kept")
precondition(ImportedFileNames.count == 0)

// Nothing to remember, and nothing to answer.
ImportedFileNames.remember(nil, forPath: "/db/1.jpg")
ImportedFileNames.remember("", forPath: "/db/1.jpg")
ImportedFileNames.remember("a.jpg", forPath: nil)
ImportedFileNames.remember("a.jpg", forPath: "")
precondition(ImportedFileNames.count == 0)
precondition(ImportedFileNames.name(forPath: nil) == nil)
precondition(ImportedFileNames.name(forPath: "/never/asked") == nil)

// The same path twice keeps the last name and stays one entry.
ImportedFileNames.remember("first.jpg", forPath: "/db/2.jpg")
ImportedFileNames.remember("second.jpg", forPath: "/db/2.jpg")
precondition(ImportedFileNames.count == 1)
precondition(ImportedFileNames.name(forPath: "/db/2.jpg") == "second.jpg")

// An entry nobody takes is dropped once the table is well past a batch, and the
// newest are the ones kept.
ImportedFileNames.forgetAll()
for index in 0..<20_100 {
    ImportedFileNames.remember("f\(index).jpg", forPath: "/db/\(index).jpg")
}
precondition(ImportedFileNames.count == 20_000, "\(ImportedFileNames.count)")
precondition(ImportedFileNames.name(forPath: "/db/0.jpg") == nil, "the oldest was kept")
precondition(ImportedFileNames.name(forPath: "/db/20099.jpg") == "f20099.jpg")
ImportedFileNames.forgetAll()
precondition(ImportedFileNames.count == 0)

print("PASS: the name is kept once, taken once, and a table nobody drains does not grow without end")
'''
with tempfile.TemporaryDirectory(prefix='horos-imported-names-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(source)
    subprocess.run(['xcrun', 'swiftc', str(root / 'Horos/Sources/ImportedFileNames.swift'),
                    str(p / 'main.swift'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the database keeps the arrival name for a file that is not DICOM, and the reader '
      'makes the identity out of it')
