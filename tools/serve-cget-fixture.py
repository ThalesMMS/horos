#!/usr/bin/env python3
"""A conformant C-GET SCP that records the roles the requestor proposed.

A C-GET returns its images as C-STORE sub-operations **on the association the
retrieval already opened**, which only works when the requestor proposed the
storage SOP classes with the Storage SCP role. This server exists to say two
things a peer cannot otherwise be asked:

  - exactly which presentation contexts arrived and what SCU/SCP role selection
    each one carried, straight out of the A-ASSOCIATE-RQ;
  - whether the retrieval that follows is satisfied on that same association,
    with no second association opened back to the requestor.

The study it serves is synthetic and mixed on purpose - CT, MR, US and one
multiframe US instance - and any instance can be made to fail with a chosen
status, so that a partial retrieval can be told apart from a complete one.
"""
import argparse
import copy
from io import BytesIO
import json
import threading
import time
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (CTImageStorage, ExplicitVRLittleEndian, MRImageStorage,
                         UltrasoundImageStorage, UltrasoundMultiFrameImageStorage,
                         generate_uid)
from pynetdicom.dsutils import encode
from pynetdicom.dimse_primitives import C_STORE
from pynetdicom import AE, ALL_TRANSFER_SYNTAXES, evt, build_role
from pynetdicom.sop_class import (PatientRootQueryRetrieveInformationModelFind,
                                  PatientRootQueryRetrieveInformationModelGet,
                                  StudyRootQueryRetrieveInformationModelFind,
                                  StudyRootQueryRetrieveInformationModelGet, Verification)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence', type=Path, help='directory for the result file')
parser.add_argument('--port', type=int, default=11193)
parser.add_argument('--bind', default='127.0.0.1', help='address to listen on; use ::1 for the IPv6 loopback')
parser.add_argument('--aetitle', default='CGETFIX')
parser.add_argument('--fail-instance', action='append', default=[],
                    help='instance number to answer with --fail-status; repeatable')
parser.add_argument('--fail-status', type=lambda v: int(v, 0), default=0xC000,
                    help='DIMSE status for failed sub-operations (default 0xC000)')
parser.add_argument('--first-size', type=int, default=32)
parser.add_argument('--instance-delay', type=float, default=0)
parser.add_argument('--stall-after', type=int, default=-1, help='ignore cancellation and pause 30s after this many objects')
parser.add_argument('--fail-image-query', action='store_true', help='refuse IMAGE inventory queries while allowing retrieval')
parser.add_argument('--instances', type=int, default=6, help='6..50 synthetic instances; extra instances are CT')
parser.add_argument('--omit-instance', type=int, help='leave one advertised instance unsent')
parser.add_argument('--duplicate-instance', type=int, help='send this instance twice')
parser.add_argument('--mismatch-instance', type=int, help='send a dataset UID different from its C-STORE request UID')
parser.add_argument('--repair-flag', type=Path, help='when this file exists, disable omit/duplicate/mismatch faults')
arguments = parser.parse_args()
if not 6 <= arguments.instances <= 50: parser.error('instances must be between 6 and 50')
for number in (arguments.omit_instance, arguments.duplicate_instance, arguments.mismatch_instance):
    if number is not None and not 1 <= number <= arguments.instances: parser.error('fault instance outside fixture')
arguments.evidence.mkdir(parents=True, exist_ok=True)

STUDY = generate_uid()
PATIENT_ID = 'CGET-27'
PATIENT_NAME = 'CGET^FIXTURE'

# modality, SOP class, series number, frames
PLAN = [
    ('CT', CTImageStorage, 1, 1),
    ('CT', CTImageStorage, 1, 1),
    ('MR', MRImageStorage, 2, 1),
    ('MR', MRImageStorage, 2, 1),
    ('US', UltrasoundImageStorage, 3, 1),
    ('US', UltrasoundMultiFrameImageStorage, 4, 8),
]
PLAN += [('CT', CTImageStorage, 1, 1)] * (arguments.instances - len(PLAN))
SERIES = {}


def instance(number, modality, sop_class, series_number, frames):
    series = SERIES.setdefault(series_number, generate_uid())
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = sop_class
    dataset.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = dataset.file_meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = STUDY
    dataset.SeriesInstanceUID = series
    dataset.PatientName = PATIENT_NAME
    dataset.PatientID = PATIENT_ID
    dataset.StudyDescription = 'C-GET role fixture'
    dataset.SeriesDescription = '%s series %d' % (modality, series_number)
    dataset.Modality = modality
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = number
    dataset.Rows = dataset.Columns = arguments.first_size if number == 1 else 32
    dataset.BitsAllocated = 8 if modality == 'US' else 16
    dataset.BitsStored = dataset.BitsAllocated
    dataset.HighBit = dataset.BitsStored - 1
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    if frames > 1:
        dataset.NumberOfFrames = frames
    kind = numpy.uint8 if dataset.BitsAllocated == 8 else numpy.uint16
    dataset.PixelData = numpy.full((frames, dataset.Rows, dataset.Columns), number, dtype=kind).tobytes()
    return dataset


INSTANCES = [instance(n + 1, *plan) for n, plan in enumerate(PLAN)]
FAILING = {int(value) for value in arguments.fail_instance}

record = {
    'study': STUDY,
    'patientID': PATIENT_ID,
    'instances': [{'number': d.InstanceNumber, 'modality': d.Modality,
                   'sopClass': str(d.SOPClassUID), 'sopInstance': str(d.SOPInstanceUID),
                   'frames': int(getattr(d, 'NumberOfFrames', 1))} for d in INSTANCES],
    'associations': [],
}
lock = threading.Lock()


def on_requested(event):
    """Every presentation context of the A-ASSOCIATE-RQ, with its role selection.

    Read straight off the request primitive, so what is recorded is what came in
    on the wire and not what this server decided to accept.
    """
    requestor = event.assoc.requestor
    roles = {str(uid): (bool(item.scu_role), bool(item.scp_role))
             for uid, item in (requestor.role_selection or {}).items()}
    contexts = []
    for context in requestor.requested_contexts:
        scu, scp = roles.get(str(context.abstract_syntax), (None, None))
        contexts.append({'abstractSyntax': str(context.abstract_syntax),
                         'proposedSCU': scu, 'proposedSCP': scp,
                         'roleSelectionSent': str(context.abstract_syntax) in roles})
    entry = {
        'callingAET': str(requestor.ae_title),
        'calledAET': str(event.assoc.acceptor.ae_title),
        'contexts': contexts,
        'roleSelectionItems': len(roles),
    }
    with lock:
        record['associations'].append(entry)
        arguments.evidence.joinpath('cget-negotiation.json').write_text(
            json.dumps(record, indent=2))
    print('association from %s: %d contexts, %d role selection items'
          % (requestor.ae_title, len(contexts), len(roles)), flush=True)


def on_find(event):
    """Enough of a C-FIND for a retrieval to find this study and ask for it."""
    query = event.identifier
    level = str(getattr(query, 'QueryRetrieveLevel', 'STUDY'))
    wanted = str(getattr(query, 'PatientID', '') or '')
    if wanted and wanted != PATIENT_ID:
        print('C-FIND %s for %r: no match' % (level, wanted), flush=True)
        return
    wanted_study = str(getattr(query, 'StudyInstanceUID', '') or '')
    if wanted_study and wanted_study != STUDY:
        print('C-FIND %s for study %r: no match' % (level, wanted_study), flush=True)
        return

    if level == 'IMAGE':
        if arguments.fail_image_query:
            yield 0xA900, None
            return
        wanted_series = str(getattr(query, 'SeriesInstanceUID', '') or '')
        answers = []
        for d in INSTANCES:
            if wanted_series and wanted_series != str(d.SeriesInstanceUID): continue
            answer = Dataset()
            answer.QueryRetrieveLevel = 'IMAGE'
            for key in ('StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID', 'SOPClassUID', 'InstanceNumber'):
                setattr(answer, key, getattr(d, key))
            answers.append(answer)
    elif level == 'SERIES':
        answers = []
        for number, uid in sorted(SERIES.items()):
            of_series = [d for d in INSTANCES if d.SeriesInstanceUID == uid]
            answer = Dataset()
            answer.QueryRetrieveLevel = 'SERIES'
            answer.PatientID = PATIENT_ID
            answer.PatientName = PATIENT_NAME
            answer.StudyInstanceUID = STUDY
            answer.SeriesInstanceUID = uid
            answer.SeriesNumber = number
            answer.Modality = of_series[0].Modality
            answer.SeriesDescription = of_series[0].SeriesDescription
            answer.NumberOfSeriesRelatedInstances = len(of_series)
            answers.append(answer)
    else:
        answer = Dataset()
        answer.QueryRetrieveLevel = 'STUDY'
        answer.PatientID = PATIENT_ID
        answer.PatientName = PATIENT_NAME
        answer.StudyInstanceUID = STUDY
        answer.StudyDescription = 'C-GET role fixture'
        answer.StudyDate = '20260101'
        answer.StudyTime = '120000'
        answer.AccessionNumber = 'CGET27'
        answer.ModalitiesInStudy = ['CT', 'MR', 'US']
        answer.NumberOfStudyRelatedInstances = len(INSTANCES)
        answer.NumberOfStudyRelatedSeries = len(SERIES)
        answer.StudyID = '27'
        answers = [answer]

    print('C-FIND %s: %d answer(s)' % (level, len(answers)), flush=True)
    for answer in answers:
        yield 0xFF00, answer


def on_get(event):
    """Answer the C-GET with the whole study, one sub-operation per instance."""
    query = event.identifier
    wanted_study = str(getattr(query, 'StudyInstanceUID', '') or '')
    wanted_series = str(getattr(query, 'SeriesInstanceUID', '') or '')
    raw_uids = getattr(query, 'SOPInstanceUID', '')
    wanted_uids = {str(x) for x in raw_uids} if not isinstance(raw_uids, str) else set(raw_uids.split('\\')) - {''}
    matching = [d for d in INSTANCES if (not wanted_study or str(d.StudyInstanceUID) == wanted_study)
                and (not wanted_series or str(d.SeriesInstanceUID) == wanted_series)
                and (not wanted_uids or str(d.SOPInstanceUID) in wanted_uids)]
    faulty = not (arguments.repair_flag and arguments.repair_flag.exists())
    if faulty:
        matching = [d for d in matching if d.InstanceNumber != arguments.omit_instance]
        matching = [item for d in matching for item in ([d, d] if d.InstanceNumber == arguments.duplicate_instance else [d])]
    with lock:
        record.setdefault('retrievals', []).append({'level': str(query.QueryRetrieveLevel), 'study': wanted_study,
            'series': wanted_series, 'requestedUIDs': sorted(wanted_uids), 'faulty': faulty,
            'sentPlan': [str(d.SOPInstanceUID) for d in matching]})
    original_send = event.assoc.dimse.send_msg
    def send_with_fault(primitive, context_id):
        if faulty and isinstance(primitive, C_STORE) and primitive.DataSet is not None:
            original = next((d for d in matching if str(d.SOPInstanceUID) == str(primitive.AffectedSOPInstanceUID)), None)
            if original is not None and original.InstanceNumber == arguments.mismatch_instance:
                damaged = copy.deepcopy(original)
                damaged.SOPInstanceUID = generate_uid()
                syntax = event.assoc._accepted_cx[context_id].transfer_syntax[0]
                primitive.DataSet = BytesIO(encode(damaged, syntax.is_implicit_VR, syntax.is_little_endian, syntax.is_deflated))
        return original_send(primitive, context_id)
    event.assoc.dimse.send_msg = send_with_fault
    try:
        yield len(matching)
        for offset, dataset in enumerate(matching):
            if offset == arguments.stall_after: time.sleep(30)
            deadline = time.monotonic() + arguments.instance_delay
            cancelled = False
            while time.monotonic() < deadline:
                # pynetdicom consumes the queued C-CANCEL when it is observed.
                # Keep that observation instead of querying it a second time.
                if event.is_cancelled:
                    cancelled = True
                    break
                time.sleep(.02)
            if cancelled or event.is_cancelled:
                yield 0xFE00, None
                return
            if dataset.InstanceNumber in FAILING:
                failure = Dataset()
                failure.Status = arguments.fail_status
                failure.FailedSOPInstanceUIDList = [str(dataset.SOPInstanceUID)]
                print('instance %d refused with 0x%04X' % (dataset.InstanceNumber,
                                                           arguments.fail_status), flush=True)
                yield arguments.fail_status, failure
            else:
                yield 0xFF00, dataset
    finally:
        event.assoc.dimse.send_msg = original_send


def on_released(event):
    with lock:
        if record['associations']:
            record['associations'][-1]['released'] = True
        arguments.evidence.joinpath('cget-negotiation.json').write_text(
            json.dumps(record, indent=2))
    print('association released', flush=True)


def on_dimse(event):
    command = event.message.command_set
    item = {'event': event.message.__class__.__name__, 'time': time.monotonic()}
    for key in ('MessageID', 'MessageIDBeingRespondedTo', 'Status',
                'NumberOfRemainingSuboperations', 'NumberOfCompletedSuboperations',
                'NumberOfFailedSuboperations', 'NumberOfWarningSuboperations', 'AffectedSOPInstanceUID'):
        value = command.get(key)
        if value is not None: item[key] = str(value)
    with lock:
        record.setdefault('timeline', []).append(item)
        arguments.evidence.joinpath('cget-negotiation.json').write_text(json.dumps(record, indent=2))


handlers = [(evt.EVT_DIMSE_RECV, on_dimse), (evt.EVT_DIMSE_SENT, on_dimse), (evt.EVT_ACCEPTED, on_requested), (evt.EVT_C_GET, on_get),
            (evt.EVT_C_FIND, on_find),
            (evt.EVT_RELEASED, on_released), (evt.EVT_CONN_CLOSE, on_released)]

ae = AE(ae_title=arguments.aetitle)
ae.add_supported_context(Verification, ALL_TRANSFER_SYNTAXES)
for model in (StudyRootQueryRetrieveInformationModelGet,
              PatientRootQueryRetrieveInformationModelGet,
              StudyRootQueryRetrieveInformationModelFind,
              PatientRootQueryRetrieveInformationModelFind):
    ae.add_supported_context(model, ALL_TRANSFER_SYNTAXES)
# The storage contexts are the ones the sub-operations travel on, and this
# server has to accept the requestor in the Storage SCP role for them - which is
# the whole point of the role selection the requestor proposes. Without this the
# association still succeeds and every sub-operation fails, which looks exactly
# like a broken requestor and is not one.
for sop_class in {str(d.SOPClassUID) for d in INSTANCES}:
    ae.add_supported_context(sop_class, ALL_TRANSFER_SYNTAXES, scu_role=False, scp_role=True)

print('study %s' % STUDY)
print('patient %s / %s' % (PATIENT_NAME, PATIENT_ID))
for entry in record['instances']:
    print('  instance %d %s %s frames=%d' % (entry['number'], entry['modality'],
                                             entry['sopClass'], entry['frames']))
print('%s listening on %s port %d' % (arguments.aetitle, arguments.bind, arguments.port), flush=True)
try:
    ae.start_server((arguments.bind, arguments.port), evt_handlers=handlers)
except KeyboardInterrupt:
    pass
finally:
    arguments.evidence.joinpath('cget-negotiation.json').write_text(json.dumps(record, indent=2))
