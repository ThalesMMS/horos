#!/usr/bin/env python3
"""Exercise a disposable loopback Horos listener with synthetic files and bad PDUs.

Requires pydicom and pynetdicom. Use generate-jpeg-series-fixture.py in an empty
directory and an isolated development database. Save stdout beside the app log.
This intentionally aborts associations; never point it at a production listener.
"""
import argparse
import json
import time
from pathlib import Path

import pydicom
from pynetdicom import AE
from pynetdicom.sop_class import Verification
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path)
parser.add_argument('--port', type=int, default=11272)
parser.add_argument('--called', default='PDVTEST')
parser.add_argument('--timeout-wait', type=float, default=13)
args = parser.parse_args()
datasets = [pydicom.dcmread(path) for path in sorted(args.fixture.glob('*.dcm'))]
if not datasets or any(ds.PatientID != 'LOCAL-JPEG-SERIES' for ds in datasets):
    raise SystemExit('Use only the generated JPEG series fixture')


def associate(storage=False):
    ae = AE(ae_title='PDVFAULT' if not storage else 'PDVVALID')
    ae.add_requested_context(Verification)
    if storage:
        for sop in sorted({str(ds.SOPClassUID) for ds in datasets}):
            ae.add_requested_context(sop, [ExplicitVRLittleEndian, ImplicitVRLittleEndian])
    association = ae.associate('127.0.0.1', args.port, ae_title=args.called)
    if not association.is_established:
        raise RuntimeError('Loopback association refused')
    return association


for stage in ('before-faults', 'after-faults'):
    a = associate(storage=True)
    statuses = []
    try:
        for ds in datasets:
            result = a.send_c_store(ds)
            statuses.append(int(result.Status) if 'Status' in result else None)
        a.release()
        print(json.dumps({'stage': stage, 'statuses': statuses, 'released': a.is_released}), flush=True)
        if any(status != 0 for status in statuses) or not a.is_released:
            raise RuntimeError('Valid reception failed')
    finally:
        if a.is_established:
            a.abort()
    if stage == 'after-faults':
        break
    for mode in ('peer-abort', 'timeout', 'invalid-pdu'):
        a = associate()
        try:
            if mode == 'peer-abort':
                a.abort()
            elif mode == 'timeout':
                time.sleep(args.timeout_wait)
            else:
                # Unknown PDU type, six-byte header, empty payload. Deliberately
                # bypass the encoder to exercise Horos's actual receive parser.
                a.dul.socket.socket.sendall(bytes([0x99, 0, 0, 0, 0, 0]))
                time.sleep(2)
            print(json.dumps({'fault': mode, 'aborted': a.is_aborted}), flush=True)
        finally:
            if a.is_established:
                a.abort()
