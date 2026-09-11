#!/usr/bin/env python3
"""A C-MOVE SCP that sends a mixed single- and multi-frame study, and says what
it sent.

A C-MOVE has the server open a second association to the destination and store
the instances there, so the requestor never sees the transfer: it sees a count.
Whether those counts and what actually arrived agree is the question, and it
needs a server that writes down every instance it sent and the status that came
back for it.

The study is deliberately mixed - 2 CT, 1 MR, 1 single-frame US and two
ultrasound multiframes of 8 and 12 frames, so 6 instances and 24 frames - and a
count of instances cannot be mistaken for a count of frames.

Held back and refused are not the same thing. A held-back instance is never
offered, so the move is complete as far as the protocol is concerned and the
requestor has no way to know anything is missing. A refused one is offered under
a SOP class the store association has no presentation context for: the C-STORE
sub-operation fails the way it would against a destination that will not take the
instance, the failure is counted, the move carries on, and the final response
carries the failure count the requestor is supposed to report.
"""
import argparse
import copy
import json
import threading
import time
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (CTImageStorage, ExplicitVRLittleEndian, MRImageStorage,
                         UltrasoundImageStorage, UltrasoundMultiFrameImageStorage,
                         generate_uid)
from pynetdicom import AE, ALL_TRANSFER_SYNTAXES, evt
from pynetdicom.sop_class import (PatientRootQueryRetrieveInformationModelFind,
                                  PatientRootQueryRetrieveInformationModelMove,
                                  StudyRootQueryRetrieveInformationModelFind,
                                  StudyRootQueryRetrieveInformationModelMove, Verification)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence', type=Path, help='directory for the result file')
parser.add_argument('--port', type=int, default=11203)
parser.add_argument('--aetitle', default='CMOVEFIX')
parser.add_argument('--destination', default='HOROSDEV',
                    help='AE title the move destination is known by')
parser.add_argument('--destination-address', default='127.0.0.1')
parser.add_argument('--destination-port', type=int, default=11112)
parser.add_argument('--hold-back', action='append', default=[],
                    help='instance number to leave out of the move altogether; repeatable')
parser.add_argument('--refuse', action='append', default=[],
                    help='instance number whose C-STORE sub-operation must fail while the move '
                         'carries on; repeatable')
parser.add_argument('--first-size', type=int, default=32, help='square dimensions of the first synthetic object')
parser.add_argument('--instance-delay', type=float, default=0, help='pause before each object, observing C-CANCEL')
parser.add_argument('--stall-after', type=int, default=-1, help='ignore cancellation and pause 30s after this many objects')
parser.add_argument('--instances', type=int, default=6)
parser.add_argument('--duplicate-instance', type=int)
parser.add_argument('--repair-flag', type=Path)
parser.add_argument('--fail-image-query', action='store_true')
arguments = parser.parse_args()
if not 6 <= arguments.instances <= 50: parser.error('instances must be between 6 and 50')
arguments.evidence.mkdir(parents=True, exist_ok=True)

STUDY = generate_uid()
PATIENT_ID = 'CMOVE-178'
PATIENT_NAME = 'CMOVE^FIXTURE'

# modality, SOP class, series number, frames
PLAN = [
    ('CT', CTImageStorage, 1, 1),
    ('CT', CTImageStorage, 1, 1),
    ('MR', MRImageStorage, 2, 1),
    ('US', UltrasoundImageStorage, 3, 1),
    ('US', UltrasoundMultiFrameImageStorage, 4, 8),
    ('US', UltrasoundMultiFrameImageStorage, 4, 12),
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
    dataset.StudyDescription = 'C-MOVE completeness fixture'
    dataset.SeriesDescription = '%s series %d' % (modality, series_number)
    dataset.Modality = modality
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = number
    size = arguments.first_size if number == 1 else 32
    dataset.Rows = dataset.Columns = size
    dataset.BitsAllocated = 8 if modality == 'US' else 16
    dataset.BitsStored = dataset.BitsAllocated
    dataset.HighBit = dataset.BitsStored - 1
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    if frames > 1:
        dataset.NumberOfFrames = frames
    kind = numpy.uint8 if dataset.BitsAllocated == 8 else numpy.uint16
    dataset.PixelData = numpy.full((frames, size, size), number, dtype=kind).tobytes()
    return dataset


INSTANCES = [instance(n + 1, *plan) for n, plan in enumerate(PLAN)]
HELD_BACK = {int(value) for value in arguments.hold_back}
REFUSED = {int(value) for value in arguments.refuse}
# A private SOP class, so the store association cannot have a context for it.
UNSUPPORTED_SOP_CLASS = '1.2.826.0.1.3680043.10.1337.178.1'
TOTAL_FRAMES = sum(int(getattr(d, 'NumberOfFrames', 1)) for d in INSTANCES)

record = {
    'study': STUDY,
    'patientID': PATIENT_ID,
    'instances': [{'number': d.InstanceNumber, 'modality': d.Modality,
                   'sopInstance': str(d.SOPInstanceUID),
                   'frames': int(getattr(d, 'NumberOfFrames', 1))} for d in INSTANCES],
    'totalFrames': TOTAL_FRAMES,
    'heldBack': sorted(HELD_BACK),
    'refused': sorted(REFUSED),
    'moves': [],
    'timeline': [],
}
lock = threading.Lock()


def save():
    arguments.evidence.joinpath('cmove-sent.json').write_text(json.dumps(record, indent=2))


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
        answer.StudyDescription = 'C-MOVE completeness fixture'
        answer.StudyDate = '20260101'
        answer.StudyTime = '120000'
        answer.AccessionNumber = 'CMOVE178'
        answer.ModalitiesInStudy = ['CT', 'MR', 'US']
        answer.NumberOfStudyRelatedInstances = len(INSTANCES)
        answer.NumberOfStudyRelatedSeries = len(SERIES)
        answer.StudyID = '178'
        answers = [answer]

    print('C-FIND %s: %d answer(s)' % (level, len(answers)), flush=True)
    for answer in answers:
        yield 0xFF00, answer


def on_move(event):
    """Send everything that is not held back to the destination."""
    if event.move_destination != arguments.destination:
        print('C-MOVE to unknown destination %r' % event.move_destination, flush=True)
        yield None, None
        return

    yield (arguments.destination_address, arguments.destination_port,
           {'evt_handlers': [(evt.EVT_DIMSE_RECV, on_dimse), (evt.EVT_DIMSE_SENT, on_dimse),
                             (evt.EVT_RELEASED, on_released)]})
    query = event.identifier
    study = str(getattr(query, 'StudyInstanceUID', '') or '')
    series = str(getattr(query, 'SeriesInstanceUID', '') or '')
    raw = getattr(query, 'SOPInstanceUID', '') or ''
    uids = set(raw.split('\\')) - {''} if isinstance(raw, str) else {str(x) for x in raw}
    repaired = arguments.repair_flag and arguments.repair_flag.exists()
    offering = [d for d in INSTANCES if (repaired or d.InstanceNumber not in HELD_BACK)
                and (not study or str(d.StudyInstanceUID) == study)
                and (not series or str(d.SeriesInstanceUID) == series)
                and (not uids or str(d.SOPInstanceUID) in uids)]
    if not repaired:
        offering = [item for d in offering for item in ([d,d] if d.InstanceNumber == arguments.duplicate_instance else [d])]
    yield len(offering)

    entry = {'destination': event.move_destination, 'offered': len(offering), 'requestedUIDs': sorted(uids), 'level': str(query.QueryRetrieveLevel),
             'heldBack': sorted(HELD_BACK), 'refused': sorted(REFUSED),
             'refusedInstances': [], 'sent': []}
    with lock:
        record['moves'].append(entry)
        save()

    print('C-MOVE to %s: offering %d of %d instances (%d held back, %d to be refused)'
          % (event.move_destination, len(offering), len(INSTANCES), len(HELD_BACK), len(REFUSED)),
          flush=True)
    for offset, dataset in enumerate(offering):
        if offset == arguments.stall_after: time.sleep(30)
        deadline = time.monotonic() + arguments.instance_delay
        cancelled = False
        while time.monotonic() < deadline:
            if event.is_cancelled:
                cancelled = True
                break
            time.sleep(0.01)
        cancelled = cancelled or event.is_cancelled
        if cancelled:
            with lock:
                record['timeline'].append({'event': 'cancel-recognized', 'time': time.monotonic()})
                save()
            yield 0xFE00, None
            return
        if dataset.InstanceNumber in REFUSED and not repaired:
            # Offer it under a SOP class the store association has no presentation
            # context for. The C-STORE sub-operation then fails the way it would
            # against a destination that will not take the instance, the failure is
            # counted, and the move carries on to the next one.
            refused = copy.deepcopy(dataset)
            refused.SOPClassUID = UNSUPPORTED_SOP_CLASS
            refused.file_meta.MediaStorageSOPClassUID = UNSUPPORTED_SOP_CLASS
            entry['refusedInstances'].append({'number': dataset.InstanceNumber,
                                              'sopInstance': str(dataset.SOPInstanceUID),
                                              'frames': int(getattr(dataset, 'NumberOfFrames', 1))})
            with lock:
                save()
            print('  instance %d offered under an unsupported SOP class' % dataset.InstanceNumber,
                  flush=True)
            yield 0xFF00, refused
            continue
        entry['sent'].append({'number': dataset.InstanceNumber,
                              'sopInstance': str(dataset.SOPInstanceUID),
                              'frames': int(getattr(dataset, 'NumberOfFrames', 1))})
        with lock:
            save()
        yield 0xFF00, dataset


def on_dimse(event):
    command = event.message.command_set
    item = {'event': event.message.__class__.__name__, 'time': time.monotonic(),
            'requestor': event.assoc.is_requestor}
    for key in ('MessageID', 'MessageIDBeingRespondedTo', 'AffectedSOPInstanceUID', 'Status',
                'NumberOfRemainingSuboperations', 'NumberOfCompletedSuboperations',
                'NumberOfFailedSuboperations', 'NumberOfWarningSuboperations'):
        value = command.get(key)
        if value is not None: item[key] = str(value)
    with lock:
        record['timeline'].append(item)
        save()


def on_released(event):
    with lock:
        record['timeline'].append({'event': 'association-released', 'time': time.monotonic(),
                                   'requestor': event.assoc.is_requestor})
        save()


handlers = [(evt.EVT_C_FIND, on_find), (evt.EVT_C_MOVE, on_move),
            (evt.EVT_DIMSE_RECV, on_dimse), (evt.EVT_DIMSE_SENT, on_dimse),
            (evt.EVT_RELEASED, on_released)]

ae = AE(ae_title=arguments.aetitle)
ae.add_supported_context(Verification, ALL_TRANSFER_SYNTAXES)
for model in (StudyRootQueryRetrieveInformationModelFind,
              PatientRootQueryRetrieveInformationModelFind,
              StudyRootQueryRetrieveInformationModelMove,
              PatientRootQueryRetrieveInformationModelMove):
    ae.add_supported_context(model, ALL_TRANSFER_SYNTAXES)
for sop_class in {str(d.SOPClassUID) for d in INSTANCES}:
    ae.add_requested_context(sop_class, ALL_TRANSFER_SYNTAXES)

print('study %s' % STUDY)
print('patient %s / %s' % (PATIENT_NAME, PATIENT_ID))
for entry in record['instances']:
    print('  instance %d %s frames=%d%s' % (entry['number'], entry['modality'], entry['frames'],
                                            '  (held back)' if entry['number'] in HELD_BACK else ''))
print('%d instances, %d frames in all' % (len(INSTANCES), TOTAL_FRAMES))
print('%s listening on port %d; destination %s at %s:%d'
      % (arguments.aetitle, arguments.port, arguments.destination,
         arguments.destination_address, arguments.destination_port), flush=True)
save()
try:
    ae.start_server(('127.0.0.1', arguments.port), evt_handlers=handlers)
except KeyboardInterrupt:
    pass
finally:
    save()
