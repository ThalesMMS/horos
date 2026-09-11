#!/usr/bin/env python3
"""Serve a synthetic study over loopback C-FIND and WADO, for native retrieve tests.

A WADO retrieval in Horos is a C-FIND at IMAGE level followed by one HTTP GET per
instance, so exercising it needs both halves. This provides them over loopback
against data it generates itself, and records what was asked for.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pydicom import dcmread
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
from pynetdicom import AE, evt
from pynetdicom.sop_class import Verification
from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind as FIND

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path, help='directory for the generated study')
parser.add_argument('evidence', type=Path, help='directory for the result file')
parser.add_argument('--dicom-port', type=int, default=11121)
parser.add_argument('--wado-port', type=int, default=11122)
parser.add_argument('--aetitle', default='WADOFIX')
parser.add_argument('--series', type=int, default=2)
parser.add_argument('--instances', type=int, default=4, help='instances per series')
parser.add_argument('--odd-length-series-uids', action='store_true', help='exercise DICOM UI NUL padding')
parser.add_argument('--strict', action='store_true',
                    help='answer only hierarchical queries, refusing relational ones')
parser.add_argument('--refuse-instances', type=int, default=0,
                    help='refuse this many instances over WADO, to leave a retrieval incomplete')
parser.add_argument('--truncate-instances', type=int, default=0,
                    help='answer this many instances with the first half of the file and a '
                         'matching Content-Length - a transfer that succeeds and delivers a '
                         'file that is not whole')
parser.add_argument('--truncate-to-bytes', type=int, default=0,
                    help='with --truncate-instances, keep this many bytes instead of half the '
                         'file; below 132 the reply has no DICOM magic at all')
parser.add_argument('--find-delay', type=float, default=0.0,
                    help='seconds to wait before answering each IMAGE level C-FIND, so a '
                         'retrieval starts downloading while the query is still running')
parser.add_argument('--fail-once', type=int, default=0,
                    help='answer 503 to this many instances the first time each is asked for, '
                         'and serve them on any later request - a transient failure')
parser.add_argument('--http-delay', type=float, default=0, help='delay responses after instance 1 for cancellation tests')
parser.add_argument('--repair-flag', type=Path, help='stop refusing configured instances when this file exists')
args = parser.parse_args()
for port in (args.dicom_port, args.wado_port):
    if port != 0 and not 1024 <= port <= 65535:
        parser.error('Use unprivileged ports, or 0 for automatic allocation')
if not 1 <= args.series <= 20 or not 1 <= args.instances <= 200:
    parser.error('Keep the fixture small')

args.fixture.mkdir(parents=True, exist_ok=True)
if not any(args.fixture.glob('*.dcm')):
    study = generate_uid()
    for series_number in range(1, args.series + 1):
        series = generate_uid()
        if args.odd_length_series_uids and len(series) % 2 == 0:
            series = series[:-1]
        for instance in range(1, args.instances + 1):
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.SOPClassUID = CTImageStorage
            ds.SOPInstanceUID = generate_uid()
            ds.StudyInstanceUID = study
            ds.SeriesInstanceUID = series
            ds.PatientName = 'QA^WADO'
            ds.PatientID = 'LOCAL-WADO'
            ds.StudyDate = '20260909'
            ds.StudyTime = '120000'
            ds.StudyID = 'WADO'
            ds.StudyDescription = 'Synthetic WADO retrieve'
            ds.SeriesDescription = 'Synthetic series %d' % series_number
            ds.SeriesNumber = series_number
            ds.InstanceNumber = instance
            ds.Modality = 'CT'
            ds.Rows = ds.Columns = 16
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = 'MONOCHROME2'
            ds.BitsAllocated = ds.BitsStored = 16
            ds.HighBit = 15
            ds.PixelRepresentation = 0
            ds.PixelSpacing = [1, 1]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.ImagePositionPatient = [0, 0, instance]
            ds.SliceThickness = 1
            # A per-instance pattern, so a mixed-up download is visible.
            base = series_number * 1000 + instance
            ds.PixelData = b''.join(((base + n) % 4096).to_bytes(2, 'little') for n in range(256))
            ds.save_as(args.fixture / ('%d-%03d.dcm' % (series_number, instance)),
                       enforce_file_format=True)

images = [dcmread(path) for path in sorted(args.fixture.glob('*.dcm'))]
assert images
by_instance = {str(ds.SOPInstanceUID): (path, ds) for path, ds
               in zip(sorted(args.fixture.glob('*.dcm')), images)}
if not 0 <= args.refuse_instances < len(images):
    parser.error('Refuse fewer instances than the study holds')
# Named up front so the evidence says which ones a complete retrieval is missing.
refused_instances = sorted(by_instance)[:args.refuse_instances]
# Taken from the other end, so the two sets do not overlap.
if not 0 <= args.fail_once <= len(images) - args.refuse_instances:
    parser.error('Fail fewer instances than the study holds outside the refused ones')
transient_instances = sorted(by_instance)[len(by_instance) - args.fail_once:] if args.fail_once else []
already_failed = set()
# Taken from the front, after the refused ones, so the three sets do not overlap.
if not 0 <= args.truncate_instances <= len(images) - args.refuse_instances - args.fail_once:
    parser.error('Truncate fewer instances than the study holds outside the other kinds')
truncated_instances = sorted(by_instance)[args.refuse_instances:
                                          args.refuse_instances + args.truncate_instances]

args.evidence.mkdir(parents=True, exist_ok=True)
state = {'aetitle': args.aetitle, 'dicom_port': args.dicom_port, 'wado_port': args.wado_port,
         'strict': bool(args.strict), 'study': str(images[0].StudyInstanceUID),
         'expected': len(images), 'series': len({str(ds.SeriesInstanceUID) for ds in images}),
         'refused_instances': refused_instances,
         'transient_instances': transient_instances,
         'truncated_instances': truncated_instances,
         'find': [], 'wado': [], 'refused': [], 'relational': [], 'transient': [],
         'truncated': [], 'ready': False}
lock = threading.Lock()


def save():
    with lock:
        temporary = args.evidence / 'wado-results.json.tmp'
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(args.evidence / 'wado-results.json')


save()


def matches(query, ds):
    for key in ('StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID', 'PatientID'):
        value = str(getattr(query, key, '') or '')
        if value and value != str(getattr(ds, key, '')):
            return False
    return True


def handle_find(event):
    query = event.identifier
    level = str(getattr(query, 'QueryRetrieveLevel', '') or '')
    study = str(getattr(query, 'StudyInstanceUID', '') or '')
    series = str(getattr(query, 'SeriesInstanceUID', '') or '')
    with lock:
        state['find'].append({'level': level, 'study': study, 'series': series})
    save()
    if args.find_delay > 0 and level == 'IMAGE':
        time.sleep(min(args.find_delay, 30))
    # A hierarchical C-FIND carries the unique key of every level above the one
    # it asks for. Without them the query is relational, which is optional and
    # negotiated; a strictly hierarchical SCP refuses it. 0xA900 is
    # Identifier Does Not Match SOP Class, which is what such an SCP answers.
    if args.strict:
        missing = (level == 'IMAGE' and not series) or (level in ('IMAGE', 'SERIES') and not study)
        if missing:
            with lock:
                state['relational'].append({'level': level, 'study': study, 'series': series})
            save()
            yield 0xA900, None
            return
    seen = set()
    for ds in images:
        if not matches(query, ds):
            continue
        answer = Dataset()
        answer.QueryRetrieveLevel = level
        answer.StudyInstanceUID = ds.StudyInstanceUID
        if level == 'STUDY':
            key = str(ds.StudyInstanceUID)
            answer.PatientID = ds.PatientID
            answer.PatientName = ds.PatientName
            answer.StudyDate = ds.StudyDate
            answer.StudyTime = ds.StudyTime
            answer.StudyDescription = ds.StudyDescription
            answer.ModalitiesInStudy = 'CT'
            answer.NumberOfStudyRelatedInstances = len(images)
        elif level == 'SERIES':
            key = str(ds.SeriesInstanceUID)
            answer.SeriesInstanceUID = ds.SeriesInstanceUID
            answer.SeriesDescription = ds.SeriesDescription
            answer.SeriesNumber = ds.SeriesNumber
            answer.Modality = ds.Modality
            answer.NumberOfSeriesRelatedInstances = sum(
                1 for other in images if other.SeriesInstanceUID == ds.SeriesInstanceUID)
        else:
            key = str(ds.SOPInstanceUID)
            answer.SeriesInstanceUID = ds.SeriesInstanceUID
            answer.SOPInstanceUID = ds.SOPInstanceUID
            answer.InstanceNumber = ds.InstanceNumber
        if key in seen:
            continue
        seen.add(key)
        yield 0xFF00, answer
    yield 0x0000, None


class WADOHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        request_type = (query.get('requestType') or [''])[0]
        instance = (query.get('objectUID') or [''])[0]
        record = {'path': parsed.path, 'requestType': request_type, 'objectUID': instance,
                  'studyUID': (query.get('studyUID') or [''])[0],
                  'seriesUID': (query.get('seriesUID') or [''])[0],
                  'contentType': (query.get('contentType') or [''])[0],
                  'transferSyntax': (query.get('transferSyntax') or [''])[0]}
        if request_type != 'WADO' or instance not in by_instance or instance in refused_instances and not (args.repair_flag and args.repair_flag.exists()):
            with lock:
                state['refused'].append(record)
            save()
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        # A failure the client should recover from by asking again: 503 once,
        # then the instance. 404 above is the other kind, and asking again for
        # one of those is wasted work.
        with lock:
            transient = instance in transient_instances and instance not in already_failed
            if transient:
                already_failed.add(instance)
                state['transient'].append(record)
        if transient:
            save()
            self.send_response(503)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        with lock:
            state.setdefault('httpStarted', []).append({'objectUID': instance, 'time': time.monotonic()})
        save()
        if args.http_delay and int(by_instance[instance][1].InstanceNumber) > 1:
            time.sleep(min(args.http_delay, 60))
        body = by_instance[instance][0].read_bytes()
        if instance in truncated_instances:
            # Half a file, delivered as if it were whole. The transfer succeeds;
            # what arrives is not a readable DICOM object.
            body = body[:args.truncate_to_bytes] if args.truncate_to_bytes else body[:len(body) // 2]
            record['bytes'] = len(body)
            with lock:
                state['truncated'].append(record)
        else:
            with lock:
                state['wado'].append(record)
        save()
        self.send_response(200)
        self.send_header('Content-Type', 'application/dicom')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


wado = ThreadingHTTPServer(('127.0.0.1', args.wado_port), WADOHandler)
threading.Thread(target=wado.serve_forever, daemon=True).start()

ae = AE(ae_title=args.aetitle)
ae.add_supported_context(Verification)
ae.add_supported_context(FIND)
server = None
try:
    server = ae.start_server(('127.0.0.1', args.dicom_port), block=False,
                             evt_handlers=[(evt.EVT_C_FIND, handle_find)])
    # Port 0 lets the kernel allocate independent ports for concurrent tests.
    # Publish readiness only after both listeners have successfully bound.
    with lock:
        state['dicom_port'] = server.server_address[1]
        state['wado_port'] = wado.server_address[1]
        state['ready'] = True
    save()
    print('C-FIND on %d, WADO on %d, study %s, %d instances'
          % (state['dicom_port'], state['wado_port'], state['study'], len(images)), flush=True)
    threading.Event().wait()
except KeyboardInterrupt:
    pass
finally:
    if server is not None:
        server.shutdown()
    wado.shutdown()
    wado.server_close()
    with lock:
        state['ready'] = False
    save()
