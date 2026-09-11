#!/usr/bin/env python3
"""Do the tags Horos indexed say what the files say?

The index is what the browser lists, what a query answers with and what the
viewer is given before a pixel is read, and it is written once, when a file
arrives. A tag read wrong there is wrong for the life of the database and
nothing rereads it. This reads each file with pydicom - a reference reader that
shares no code with the application - and compares, instance by instance, with
the row the application wrote.

    python3 tools/check-indexed-tags.py <fixture dir> <database.sql>

Matching is by series UID and then by instance number. A multi-frame instance is
indexed as one row per frame, so a series holding one such file is compared
against the frame count instead.
"""
import argparse
import collections
import sqlite3
import sys
from pathlib import Path

import pydicom

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('fixture', type=Path, help='the directory holding the instances')
parser.add_argument('database', type=Path, help="the application's Database.sql")
arguments = parser.parse_args()

instances = sorted(arguments.fixture.glob('*.dcm'))
if not instances:
    raise SystemExit('%s holds no .dcm files' % arguments.fixture)

connection = sqlite3.connect('file:%s?mode=ro' % arguments.database, uri=True)
connection.row_factory = sqlite3.Row


by_series = collections.defaultdict(list)
for row in connection.execute(
        'select i.*, s.ZSERIESDICOMUID as seriesUID, s.ZMODALITY as seriesModality, '
        's.ZNAME as seriesName, s.ZWINDOWWIDTH as seriesWindowWidth, '
        's.ZWINDOWLEVEL as seriesWindowLevel, st.ZSTUDYINSTANCEUID as studyUID, '
        'st.ZNAME as patientName, st.ZPATIENTID as patientID '
        'from ZIMAGE i join ZSERIES s on i.ZSERIES = s.Z_PK '
        'join ZSTUDY st on s.ZSTUDY = st.Z_PK'):
    by_series[row['seriesUID']].append(row)

by_file = collections.defaultdict(list)
for path in instances:
    header = pydicom.dcmread(str(path), stop_before_pixels=True)
    by_file[str(header.SeriesInstanceUID)].append(path)

failures = []
checked = 0

for path in instances:
    dataset = pydicom.dcmread(str(path), stop_before_pixels=True)
    indexed = by_series.get(str(dataset.SeriesInstanceUID))
    if not indexed:
        failures.append('%s: nothing in the index for it' % path.name)
        continue
    frames = int(getattr(dataset, 'NumberOfFrames', 1) or 1)
    number = int(getattr(dataset, 'InstanceNumber', 1) or 1)
    if frames > 1:
        row = indexed[0]
    else:
        matching = [r for r in indexed if r['ZINSTANCENUMBER'] == number]
        if not matching:
            failures.append('%s: no row with instance number %d in its series'
                            % (path.name, number))
            continue
        row = matching[0]
    checked += 1

    def compare(what, indexed, expected):
        if indexed != expected:
            failures.append('%s: %s indexed as %r, the file says %r'
                            % (path.name, what, indexed, expected))

    compare('study instance UID', row['studyUID'], str(dataset.StudyInstanceUID))
    compare('series instance UID', row['seriesUID'], str(dataset.SeriesInstanceUID))
    compare('modality', row['ZSTOREDMODALITY'] or row['seriesModality'], str(dataset.Modality))
    # A multi-frame instance is one row per frame, and each row's instance
    # number is that frame's place in the stack, not the file's; a series of
    # separate instances is one row each.
    if frames > 1:
        compare('rows in the index', len(indexed), frames)
    else:
        compare('instance number', row['ZINSTANCENUMBER'], number)
        compare('rows in the index', len(indexed), len(by_file[str(dataset.SeriesInstanceUID)]))
    compare('patient id', row['patientID'], str(dataset.PatientID))
    # The index keeps the name as the file spells it, carets and all; the
    # browser is what turns it into "Family, Given" for the reader.
    compare('patient name', (row['patientName'] or '').strip().upper(),
            str(dataset.PatientName).strip().upper())
    compare('rows', row['ZSTOREDHEIGHT'], int(dataset.Rows))
    compare('columns', row['ZSTOREDWIDTH'], int(dataset.Columns))
    if frames > 1:
        compare('number of frames', row['ZSTOREDNUMBEROFFRAMES'] or 1, frames)

print('%d instance(s) compared against pydicom' % checked)
for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: every indexed tag says what the file says')
