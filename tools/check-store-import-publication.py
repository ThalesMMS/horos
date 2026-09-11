#!/usr/bin/env python3
"""Test permission failure and retry on a fresh, disposable development database.

The running loopback listener must use --database and have zero indexed images.
Only synthetic JPEG-series fixtures are accepted. Restores directory permissions
even if the probe fails. Requires pydicom and pynetdicom.
"""
import argparse
import json
import sqlite3
import time
from pathlib import Path

import pydicom
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian
from pynetdicom import AE

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path)
parser.add_argument('--database', type=Path, required=True, help='Private Horos Data directory')
parser.add_argument('--port', type=int, default=11272)
parser.add_argument('--called', default='LOCALTEST')
args = parser.parse_args()
database = args.database.resolve()
if not database.is_relative_to(Path(__file__).resolve().parents[1] / 'local-validation'):
    raise SystemExit('Use a disposable database under this checkout/local-validation')
datasets = [pydicom.dcmread(p) for p in sorted(args.fixture.glob('*.dcm'))]
if len(datasets) != 5 or any(ds.PatientID != 'LOCAL-JPEG-SERIES' for ds in datasets):
    raise SystemExit('Use only generate-jpeg-series-fixture.py output')


def image_count():
    with sqlite3.connect((database / 'Database.sql').as_uri() + '?mode=ro', uri=True) as connection:
        return connection.execute('SELECT COUNT(*) FROM ZIMAGE').fetchone()[0]


def send():
    ae = AE(ae_title='STOREPUBLICATION')
    ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = 10
    for sop in sorted({str(ds.SOPClassUID) for ds in datasets}):
        ae.add_requested_context(sop, [ExplicitVRLittleEndian, ImplicitVRLittleEndian])
    a = ae.associate('127.0.0.1', args.port, ae_title=args.called)
    assert a.is_established
    statuses = []
    start = time.monotonic()
    try:
        for ds in datasets:
            response = a.send_c_store(ds)
            statuses.append(response.get('Status'))
        a.release()
        assert a.is_released
    finally:
        if a.is_established:
            a.abort()
    return statuses, round(time.monotonic() - start, 3)


assert image_count() == 0, 'Use a fresh private database'
for directory in ('INCOMING.noindex', 'TEMP.noindex'):
    target = database / directory
    mode = target.stat().st_mode & 0o777
    try:
        target.chmod(0o500)
        statuses, duration = send()
        print(json.dumps({'blocked': directory, 'statuses': statuses, 'seconds': duration}), flush=True)
        assert statuses == [0xA700] * 5, 'Every unpublishable object must be refused'
        assert image_count() == 0
    finally:
        target.chmod(mode)
statuses, duration = send()
assert statuses == [0] * 5
deadline = time.monotonic() + 20
while image_count() != 8 and time.monotonic() < deadline:
    time.sleep(0.1)
assert image_count() == 8
print(json.dumps({'retry': True, 'statuses': statuses, 'seconds': duration, 'indexedImages': 8}), flush=True)
print('PASS: both storage permission failures are refused; restored permissions allow all five objects and eight image records')
