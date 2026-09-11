#!/usr/bin/env python3
"""Query and retrieve an imported synthetic localizer fixture from loopback Horos.

Generate with generate-localizer-study-fixture.py, import into an isolated
development database with NOLOCALIZER enabled, and enable its C-FIND/C-GET SCP.
No received images are written to disk. Requires pydicom, pynetdicom and numpy.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, ImplicitVRLittleEndian, UID
from pynetdicom import AE, build_role, evt
from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind as FIND
from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelGet as GET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path)
parser.add_argument('--port', type=int, default=11272)
parser.add_argument('--called', default='LOCALTEST')
parser.add_argument('--same-association', action='store_true', help='Also exercise sequential retrieval on one association')
args = parser.parse_args()
manifest = json.loads((args.fixture / 'manifest.json').read_text())
originals = {uid: pydicom.dcmread(args.fixture / entry['path'])
             for uid, entry in manifest['instances'].items()}
if any(ds.PatientID != 'LOCAL-LOCALIZER' for ds in originals.values()):
    raise SystemExit('Use only the generated localizer fixture')
received = []
errors = []


def store(event):
    ds = event.dataset
    ds.file_meta = event.file_meta
    uid = str(ds.SOPInstanceUID)
    received.append(uid)
    try:
        original = originals[uid]
        assert ds.StudyInstanceUID == original.StudyInstanceUID
        assert ds.SeriesInstanceUID == original.SeriesInstanceUID
        np.testing.assert_array_equal(ds.pixel_array, original.pixel_array)
    except Exception as error:
        errors.append(f'{uid}: {error}')
        return 0xC000
    return 0


ae = AE(ae_title='LOCALGET')
ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = 15
ae.add_requested_context(FIND)
ae.add_requested_context(GET)
ae.add_requested_context(CTImageStorage, [ExplicitVRLittleEndian, ImplicitVRLittleEndian])
def connect():
    result = ae.associate('127.0.0.1', args.port, ae_title=args.called,
                          ext_neg=[build_role(CTImageStorage, scu_role=False, scp_role=True)],
                          evt_handlers=[(evt.EVT_C_STORE, store)])
    assert result.is_established, 'Loopback association refused'
    return result


association = connect()
assert association.is_established, 'Loopback association refused'
try:
    query = Dataset()
    query.QueryRetrieveLevel = 'SERIES'
    query.StudyInstanceUID = manifest['study']
    query.SeriesInstanceUID = ''
    series = []
    final = None
    for status, ds in association.send_c_find(query, FIND):
        final = status.get('Status')
        if ds is not None:
            uid = str(ds.SeriesInstanceUID)
            assert UID(uid).is_valid
            series.append(uid)
    assert final == 0, 'C-FIND did not finish successfully'
    localizers = [uid for uid in series if uid in manifest['localizer_series']]
    assert len(localizers) == 1, f'Expected one grouped localizer series: {series}'
    assert set(series) == set(localizers + manifest['other_series'])
    assert len(series) == len(set(series))

    requests = series + list(reversed(series)) if args.same_association else series
    for uid in requests:
        if not args.same_association:
            association.release()
            assert association.is_released
            association = connect()
        received.clear()
        query.SeriesInstanceUID = uid
        expected = {sop for sop, entry in manifest['instances'].items()
                    if entry['series'] in (manifest['localizer_series'] if uid in localizers else [uid])}
        final_status = None
        for status, _ in association.send_c_get(query, GET):
            final_status = status
        assert final_status is not None and final_status.get('Status') == 0, str(final_status)
        assert not errors, errors
        assert set(received) == expected, (received, sorted(expected))
        assert len(received) == len(expected), 'Duplicate C-STORE suboperation'
        assert final_status.NumberOfCompletedSuboperations == len(expected)
        assert final_status.NumberOfFailedSuboperations == 0
        assert final_status.NumberOfWarningSuboperations == 0
        print(json.dumps({'series': uid, 'kind': 'localizers' if uid in localizers else 'axial',
                          'received': len(received), 'status': 0,
                          'originalUIDsAndPixels': True}), flush=True)
    association.release()
    assert association.is_released
finally:
    if association.is_established:
        association.abort()
print('PASS: grouped localizers and axial control retrieved with exact SOP identities, original series UIDs and pixels')
