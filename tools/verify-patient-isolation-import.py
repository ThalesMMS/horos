#!/usr/bin/env python3
"""Check synthetic fixture identities/pixels against the private SQLite index."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

import pydicom


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path)
parser.add_argument('database', type=Path, help='Private Horos Data directory')
parser.add_argument('--batch', choices=['first', 'second', 'all'], default='all')
args = parser.parse_args()
records = json.loads((args.fixture / 'manifest.json').read_text())
for record in records:
    assert hashlib.sha256((args.fixture / record['path']).read_bytes()).hexdigest() == record['file_sha256']
expected = {r['sop']: r for r in records if args.batch == 'all' or r['path'].startswith(args.batch + '/')}
patients = sorted({r['patient'] for r in records})
connection = sqlite3.connect((args.database / 'Database.sql').resolve().as_uri() + '?mode=ro', uri=True)
query = '''SELECT i.ZPATHNUMBER, i.ZPATHSTRING, i.ZINSTANCENUMBER,
                  st.ZPATIENTID, st.ZSTUDYINSTANCEUID, s.ZSERIESDICOMUID
           FROM ZIMAGE i JOIN ZSERIES s ON i.ZSERIES=s.Z_PK
           JOIN ZSTUDY st ON s.ZSTUDY=st.Z_PK
           WHERE st.ZPATIENTID IN (%s)''' % ','.join('?' for _ in patients)
rows = connection.execute(query, patients).fetchall()
assert len(rows) == len(expected), (len(rows), len(expected))
paths = {}
for path in (args.database / 'DATABASE.noindex').rglob('*'):
    if path.is_file():
        paths.setdefault(path.stem, []).append(path)
seen = Counter()
for number, external, instance, patient, study, series in rows:
    assert not external, 'Expected copied private fixture, not an external link'
    matches = paths.get(str(number), [])
    assert len(matches) == 1, (number, matches)
    ds = pydicom.dcmread(matches[0])
    record = expected[str(ds.SOPInstanceUID)]
    assert patient == str(ds.PatientID) == record['patient']
    assert study == str(ds.StudyInstanceUID) == record['study']
    assert series == str(ds.SeriesInstanceUID) == record['series']
    assert instance == int(ds.InstanceNumber) == record['instance']
    assert hashlib.sha256(ds.PixelData).hexdigest() == record['pixels_sha256']
    assert int(ds.pixel_array[0, 0]) == record['marker']
    seen[str(ds.SOPInstanceUID)] += 1
assert seen == Counter({sop: 1 for sop in expected})
print(f'PASS: {len(rows)} indexed instances, {len(patients)} patients; identity, pixels and original hashes match')
