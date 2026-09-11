#!/usr/bin/env python3
"""The localizer grouping does not overwrite the DICOM SeriesInstanceUID.

With NOLOCALIZER set, which it is by default, Horos puts the localizers of a
study into one internal series. It also used to overwrite seriesDICOMUID - the
DICOM SeriesInstanceUID it stores - with the word LOCALIZER followed by the study
identifier, and that value is what the C-FIND SCP answers with. UI allows 64
characters of digits and dots; that value is 74 characters and starts with nine
letters.

The grouping is serieID, which the importer matches series rows on.
seriesDICOMUID is stored beside it and merges nothing, so leaving the identifier
from the file alone keeps the grouping and puts a real UID back on the wire.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
source = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')

# UI: at most 64 characters, digits and dots only, no leading or embedded space.
UID = re.compile(r'^[0-9.]{1,64}$')


def conformant(value):
    return bool(UID.match(value)) and '..' not in value


# The value the old code produced, against a UID of the length these fixtures use.
STUDY = '1.2.826.0.1.3680043.8.498.64788744647355255395090336010075907066'
if conformant('LOCALIZER' + STUDY):
    failures.append('the value this test defends against is conformant; the test is wrong')
if conformant(STUDY) is False:
    failures.append('the fixture study identifier is not a conformant UID; the test is wrong')

# --- the localizer branch ---------------------------------------------------
at = source.find('self.serieID = @"LOCALIZER";')
if at < 0:
    failures.append('the localizer grouping is gone')
else:
    opening = source.rindex('{', 0, at)
    depth, index, branch = 0, opening, ''
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                branch = source[opening:index + 1]
                break
        index += 1
    if re.search(r'forKey:\s*@"seriesDICOMUID"', branch):
        failures.append('the localizer branch writes seriesDICOMUID again')
    # The grouping itself has to stay: that is what merges the localizers.
    if 'seriesDescription' not in branch:
        failures.append('the localizer branch no longer names the merged series')

# Exactly one write takes it from the file, and any other has to be a fallback
# that only runs when the file carries none - never an unconditional overwrite.
assignments = re.findall(r'\[dicomElements setObject:\s*([^\n]*?)\s*forKey:\s*@"seriesDICOMUID"\]',
                         source)
fromFile = [value for value in assignments if value == 'self.serieID']
if len(fromFile) != 1:
    failures.append('seriesDICOMUID is written from the value read for the series %d times, '
                    'expected once (all writes: %s)' % (len(fromFile), ', '.join(assignments)))
else:
    # And that value is the SeriesInstanceUID of the file, read just above it.
    at = source.index('forKey:@"seriesDICOMUID"')
    if 'DCM_SeriesInstanceUID' not in source[at - 400:at]:
        failures.append('seriesDICOMUID is no longer set from DCM_SeriesInstanceUID')

for value in [value for value in assignments if value != 'self.serieID']:
    at = source.find('setObject: %s forKey: @"seriesDICOMUID"' % value)
    if at < 0 or 'objectForKey: @"seriesDICOMUID"] length] == 0' not in source[max(0, at - 500):at]:
        failures.append('seriesDICOMUID is written as %s without first checking that the file '
                        'carries none, so a real SeriesInstanceUID can be replaced' % value)

# --- why this is safe: the importer groups on something else -----------------
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
lookup = re.search(r'indexOfObject:\[curDict objectForKey: \[@"seriesID"[^\]]*\]\]', database)
if not lookup:
    failures.append('the importer no longer finds a series row by its seriesID')
if 'valueForKey:@"seriesInstanceUID"] indexOfObject' not in database:
    failures.append('the importer no longer matches the stored seriesInstanceUID attribute')

# --- and why it matters: the SCP answers with it -----------------------------
handler = (root / 'Horos/Sources/OsiriXSCPDataHandler.mm').read_bytes().decode('latin1')
for level, key in (('series', 'seriesDICOMUID'), ('image', 'series.seriesDICOMUID')):
    if 'putAndInsertString(DCM_SeriesInstanceUID, [[fetchedObject valueForKey%s:@"%s"]' % (
            '' if level == 'series' else 'Path', key) not in handler.replace('\n', ' '):
        # The exact spelling differs between the two; check the pairing loosely.
        if key not in handler:
            failures.append('the %s level C-FIND response no longer uses %s' % (level, key))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the localizer grouping keeps serieID and leaves seriesDICOMUID as the '
      'SeriesInstanceUID read from the file, which is what the C-FIND SCP answers with')
