#!/usr/bin/env python3
"""Which date a study is filed under, and what happens when there is none.

The parser takes the first of AcquisitionDate, ContentDate, SeriesDate,
StudyDate that is present, pairs it with the matching time, and falls back to
1901-01-01 when none is - a marker the importer refuses to store, so a study
that carried no date is filed with none rather than with an invented one. No
step anywhere reads the file's modification time.

Measured on the development build with `tools/generate-date-precedence-fixture.py`,
five studies each carrying a different subset:

    DATES^ALL        2024-01-01   (AcquisitionDate, over three others)
    DATES^CONTENT    2023-06-01   (ContentDate, over two)
    DATES^SERIES     2023-02-02   (SeriesDate, over StudyDate)
    DATES^STUDY      2022-03-03
    DATES^NONE       none

A date that is *there* and cannot be read ended the same way as no date at all,
and said nothing: `DATES^BAD`, carrying `StudyDate = 2022XX03`, was filed without
a date and nothing recorded that the file had carried one.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
parser = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')

# --- the precedence, in order ------------------------------------------------
at = parser.find('//Acquistion Date')
end = parser.find('//Series Description', at) if at >= 0 else -1
window = parser[at:end] if at >= 0 and end > at else ''
if not window:
    failures.append('the block that chooses the study date is gone')
else:
    order = [tag for tag in re.findall(r'DCM_(AcquisitionDate|ContentDate|SeriesDate|StudyDate)', window)]
    if order != ['AcquisitionDate', 'ContentDate', 'SeriesDate', 'StudyDate']:
        failures.append('the date precedence changed: %s' % ' then '.join(order))
    times = [tag for tag in re.findall(r'DCM_(AcquisitionTime|ContentTime|SeriesTime|StudyTime)', window)]
    if times != ['AcquisitionTime', 'ContentTime', 'SeriesTime', 'StudyTime']:
        failures.append('the time precedence does not match the date precedence: %s'
                        % ' then '.join(times))
    if 'dateWithYear:1901' not in window:
        failures.append('a study with no date no longer gets the marker the importer knows to '
                        'refuse, so it will be filed under whatever is left')
    if 'could not be read' not in window:
        failures.append('a date that is present and cannot be read is dropped in silence, which '
                        'is indistinguishable from a study that never carried one')

# --- and the marker must never reach the database ----------------------------
if 'isEqualToDate: defaultDate] == NO' not in database:
    failures.append('the importer no longer refuses the no-date marker, so studies would be filed '
                    'under 1901')

# --- no clinical date may come from the file system --------------------------
code = re.sub(r'//[^\n]*', '', parser)
if 'NSFileModificationDate' in code or 'fileModificationDate' in code:
    failures.append('the parser reads a file system date; a clinical date must not come from the '
                    'file it happens to be stored in')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the study date comes from the first DICOM date that is present, a study without one is '
      'filed without one, and a date that cannot be read says so')
