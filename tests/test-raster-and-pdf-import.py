#!/usr/bin/env python3
"""A valid PNG, JPEG, GIF, BMP, TIFF or PDF becomes a series.

`-[DicomFile getImageFile]` reads tiff, tif, stk, png, jpg, jpeg, jp2, pdf, pct
and gif through NSImage and libtiff, and `-init:` reaches it whenever the caller
is not asking for DICOM only. But the incoming folder let only four kinds of file
through its own door:

    if (isDicomFile == YES ||
        (([DicomFile isFVTiffFile:srcPath] ||
          [DicomFile isTiffFile:srcPath] ||
          [DicomFile isNRRDFile:srcPath]) && ...

so a PNG, a JPEG or a PDF was refused before the reader that handles it ever saw
it. Measured on a folder of six raster files - 64x48, a white corner, red rising
across and green rising down:

    ---- import: in000005.png is not a DICOM file this database can index; deleted
    (importFilesFromIncomingDir): 1 file(s) taken from the incoming folder, 0 indexed

Only the TIFF got as far as the indexer, and it was then refused too - because
`onlyDICOM` is registered as 1 and the refusal said "was not recognised as
DICOM", of a file that had been read perfectly well.

With the door widened to what the reader handles when the database is not set to
DICOM only, and bmp added to the reader beside gif, the same six files give

    (importFilesFromIncomingDir): 6 file(s) taken from the incoming folder,
                                  6 indexed, in 0.0 s (2.1 ms per file)
      studies 1  series 1  images 6
        64x48  5.pdf / 3.bmp / 2.gif / 4.jpg / 6.tiff / 7.png

and every stored file is byte-identical to the fixture it came from. With
`onlyDICOM` left on, the refusal now says which it was:

    2.tiff is IMAGE, and this database indexes only DICOM (see the onlyDICOM preference)
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
dicomfile = (root / 'Horos/Sources/DicomFile.mm').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/DicomFile.h').read_bytes().decode('latin1')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
refusals_path = root / 'Horos/Sources/ImportRefusals.swift'
refusals = refusals_path.read_text() if refusals_path.exists() else ''

RASTER = ('tiff', 'tif', 'stk', 'png', 'jpg', 'jpeg', 'jp2', 'pdf', 'pct', 'gif', 'bmp')

# --- the reader and the test of what it reads agree ---------------------------
live = re.sub(r'//[^\n]*', '', dicomfile)
at = live.find('+ (BOOL) isImageFile:')
if at < 0:
    failures.append('nothing says which extensions the raster reader handles')
else:
    listed = set(re.findall(r'@"(\w+)"', live[at:live.find('\n}', at)]))
    for extension in RASTER:
        if extension not in listed:
            failures.append('%s is missing from the list of raster extensions' % extension)
if 'isImageFile:' not in header:
    failures.append('the test is not declared, so the database cannot use it')

at = live.find('-(short) getImageFile')
if at < 0:
    failures.append('the raster reader is gone')
else:
    body = live[at:at + 1200]
    for extension in ('png', 'jpg', 'pdf', 'gif', 'bmp', 'tiff'):
        if '@"%s"' % extension not in body:
            failures.append('the raster reader no longer handles %s' % extension)

# --- the incoming folder lets them in when it indexes more than DICOM ---------
# Comments go, and then the whitespace they leave behind. Enhanced and IVUS
# triage now sit between the DICOM test and the door; a character count from
# that assignment no longer reaches the gate. Look at the admission condition
# itself (isFVTiffFile / isImageFile), not a window from the assignment.
live = re.sub(r'//[^\n]*', '', database)
live = re.sub(r'\s+', ' ', live)
at = live.find('isDicomFile = [DicomFile isDICOMFile:srcPath')
door = live.find('[DicomFile isFVTiffFile:srcPath', at) if at >= 0 else -1
if at < 0 or door < 0:
    failures.append('the incoming folder no longer decides what to take')
else:
    # onlyDICOM is registered just before the door; isImageFile is inside it.
    gate = live[max(at, door - 200):door + 400]
    if 'isImageFile' not in gate:
        failures.append('a valid PNG, JPEG or PDF is still refused before the reader that '
                        'handles it ever sees it')
    if 'onlyDICOM' not in gate:
        failures.append('the widened door ignores the preference, so a database set to DICOM '
                        'only would take a raster in and then throw it away')

# --- and a refusal by policy does not read as a broken file -------------------
if 'indexes only DICOM' not in live:
    failures.append('a file refused because only DICOM is indexed is still called unreadable')
else:
    at = live.find('indexes only DICOM')
    window = live[max(0, at - 600):at + 1200]
    if 'refusedByPolicy' not in window:
        failures.append('the reason is built but not carried to the refusal')
    if 'refuse: newFile reason:' not in window:
        failures.append('the refusal does not take the reason it was given')
if 'refuse(_ path: String, reason: String)' not in refusals:
    failures.append('the report cannot be told a reason it could not work out for itself')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the raster and PDF formats the reader handles reach it, and a file refused by policy '
      'is not called unreadable')
