#!/usr/bin/env python3
"""Serve only the generated patient-isolation fixture over loopback C-FIND/C-GET."""
import argparse
import hashlib
import json
from pathlib import Path

from pydicom import dcmread
from pydicom.dataset import Dataset
from pydicom.uid import MRImageStorage
from pynetdicom import AE, evt
from pynetdicom.sop_class import Verification
from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind as FIND
from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelGet as GET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path)
parser.add_argument('evidence', type=Path)
parser.add_argument('--port', type=int, default=11126)
args = parser.parse_args()
if not 1024 <= args.port <= 65535:
    parser.error('Use an unprivileged port')
records = json.loads((args.fixture / 'manifest.json').read_text())
images = []
for record in records:
    path = (args.fixture / record['path']).resolve()
    assert path.is_relative_to(args.fixture.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['file_sha256']
    ds = dcmread(path)
    assert str(ds.PatientID).startswith('LOCAL-ISOLATION-')
    assert str(ds.PatientName).startswith('QA^Isolation')
    assert str(ds.SOPInstanceUID) == record['sop']
    assert ds.SOPClassUID == MRImageStorage
    images.append(ds)
assert images
args.evidence.mkdir(parents=True, exist_ok=True)
if any(args.evidence.iterdir()):
    parser.error('Use an empty evidence directory')
state = {'find': [], 'get': [], 'sent': []}


def save():
    (args.evidence / 'pacs-results.json').write_text(json.dumps(state, indent=2) + '\n')


def select(query):
    selected = images
    for key in ('PatientID', 'StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID'):
        value = str(getattr(query, key, ''))
        if value:
            selected = [d for d in selected if str(getattr(d, key, '')) in value.split('\\')]
    return selected


def find(event):
    query = event.identifier
    level = str(query.QueryRetrieveLevel)
    state['find'].append({'level': level, 'study': str(getattr(query, 'StudyInstanceUID', ''))})
    save()
    if level not in ('STUDY', 'SERIES', 'IMAGE'):
        yield 0xA900, None
        return
    selected = select(query)
    seen = set()
    for ds in selected:
        key = str(getattr(ds, {'STUDY': 'StudyInstanceUID', 'SERIES': 'SeriesInstanceUID', 'IMAGE': 'SOPInstanceUID'}[level]))
        if key in seen:
            continue
        seen.add(key)
        out = Dataset()
        out.QueryRetrieveLevel = level
        for name in ('PatientName', 'PatientID', 'PatientBirthDate', 'StudyInstanceUID', 'StudyDate', 'StudyTime', 'StudyDescription', 'StudyID'):
            setattr(out, name, getattr(ds, name, ''))
        study = [d for d in selected if d.StudyInstanceUID == ds.StudyInstanceUID]
        out.ModalitiesInStudy = 'MR'
        out.NumberOfStudyRelatedInstances = len(study)
        out.NumberOfStudyRelatedSeries = len({str(d.SeriesInstanceUID) for d in study})
        if level != 'STUDY':
            for name in ('SeriesInstanceUID', 'SeriesDescription', 'SeriesNumber', 'Modality'):
                setattr(out, name, getattr(ds, name))
            out.NumberOfSeriesRelatedInstances = sum(d.SeriesInstanceUID == ds.SeriesInstanceUID for d in selected)
        if level == 'IMAGE':
            out.SOPInstanceUID, out.InstanceNumber = ds.SOPInstanceUID, ds.InstanceNumber
        yield 0xFF00, out


def get(event):
    query = event.identifier
    selected = select(query)
    state['get'].append({'study': str(getattr(query, 'StudyInstanceUID', '')), 'series': str(getattr(query, 'SeriesInstanceUID', '')), 'count': len(selected)})
    save()
    yield len(selected)
    # Interleave different patients/series, rather than sending directory groups.
    selected.sort(key=lambda d: (int(d.InstanceNumber), str(d.PatientID), int(d.SeriesNumber)))
    for ds in selected:
        if event.is_cancelled:
            yield 0xFE00, None
            return
        state['sent'].append(str(ds.SOPInstanceUID))
        save()
        yield 0xFF00, ds


ae = AE(ae_title='HOROSISOLATION')
for context in (Verification, FIND, GET):
    ae.add_supported_context(context)
ae.add_supported_context(MRImageStorage, scu_role=False, scp_role=True)
save()
print(f'Synthetic patient isolation PACS: 127.0.0.1:{args.port}, {len(images)} instances', flush=True)
ae.start_server(('127.0.0.1', args.port), evt_handlers=[(evt.EVT_C_FIND, find), (evt.EVT_C_GET, get)])
