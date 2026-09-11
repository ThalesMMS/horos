#!/usr/bin/env python3
"""Serve a synthetic study over loopback QIDO-RS and WADO-RS (#384, common).

The DICOMweb pilot of #197 was validated against an Orthanc in a container. This
serves the same two halves a Horos DICOMweb node uses — QIDO-RS for the
hierarchy and WADO-RS for the objects — from data it generates itself, with the
standard library and pydicom, so a study can be retrieved by the application's
own client without any other infrastructure.

Loopback only, no authentication, and it records what was asked of it.

    python3 tools/serve-dicomweb-fixture.py FIXTURE EVIDENCE [--port 18044]
"""
import argparse
import json
import re
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path, help='empty directory for the generated study')
parser.add_argument('evidence', type=Path, help='directory for the request record')
parser.add_argument('--port', type=int, default=18044)
parser.add_argument('--instances', type=int, default=4)
parser.add_argument('--rows', type=int, default=64)
parser.add_argument('--columns', type=int, default=64)
parser.add_argument('--patient-name', default='SYNTHETIC^DICOMWEB384')
parser.add_argument('--patient-id', default='LOCAL-DICOMWEB-384')
args = parser.parse_args()
if not 1024 <= args.port <= 65535 or args.instances < 1:
    parser.error('a port above 1024 and at least one instance')
args.fixture.mkdir(parents=True, exist_ok=True)
if any(args.fixture.iterdir()):
    parser.error('the fixture directory must be empty: ' + str(args.fixture))
args.evidence.mkdir(parents=True, exist_ok=True)

study_uid, series_uid = generate_uid(), generate_uid()
instances = []
for index in range(args.instances):
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.is_little_endian, dataset.is_implicit_VR = True, False
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = dataset.file_meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID, dataset.SeriesInstanceUID = study_uid, series_uid
    dataset.PatientName, dataset.PatientID = args.patient_name, args.patient_id
    dataset.PatientBirthDate = '19700101'
    dataset.StudyDate, dataset.StudyTime = '20260914', '120000'
    dataset.StudyDescription = 'Synthetic DICOMweb Retrieval'
    dataset.SeriesDescription = 'DICOMweb retrieved'
    dataset.Modality, dataset.SeriesNumber, dataset.InstanceNumber = 'CT', 1, index + 1
    dataset.StudyID, dataset.AccessionNumber = '384', ''
    dataset.ImagePositionPatient = [0.0, 0.0, float(index) * 2.0]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.FrameOfReferenceUID = generate_uid() if index == -1 else study_uid
    dataset.PixelSpacing, dataset.SliceThickness = [0.5, 0.5], 2.0
    dataset.Rows, dataset.Columns = args.rows, args.columns
    dataset.SamplesPerPixel, dataset.PhotometricInterpretation = 1, 'MONOCHROME2'
    dataset.BitsAllocated, dataset.BitsStored, dataset.HighBit = 16, 16, 15
    dataset.PixelRepresentation = 1
    dataset.RescaleIntercept, dataset.RescaleSlope = -1024.0, 1.0
    dataset.WindowCenter, dataset.WindowWidth = 40.0, 400.0
    # A gradient that differs per instance, so a retrieved page is identifiable.
    gradient = numpy.linspace(0, 1000, args.rows * args.columns, dtype=numpy.int16)
    pixels = (gradient.reshape(args.rows, args.columns) + index * 200).astype(numpy.int16)
    pixels[: args.rows // 8, : args.columns // 8] = 2000
    dataset.PixelData = pixels.tobytes()
    path = args.fixture / ('instance-%03d.dcm' % index)
    dataset.save_as(path, enforce_file_format=True)
    instances.append({'path': path, 'sop': dataset.SOPInstanceUID, 'number': index + 1})

served = []
lock = threading.Lock()


def attribute(vr, value):
    return {'vr': vr, 'Value': value if isinstance(value, list) else [value]}


def study_record():
    return {
        '0020000D': attribute('UI', study_uid),
        '00100010': attribute('PN', {'Alphabetic': args.patient_name}),
        '00100020': attribute('LO', args.patient_id),
        '00100030': attribute('DA', '19700101'),
        '00080020': attribute('DA', '20260914'),
        '00080030': attribute('TM', '120000'),
        '00081030': attribute('LO', 'Synthetic DICOMweb Retrieval'),
        '00080061': attribute('CS', 'CT'),
        '00200010': attribute('SH', '384'),
        '00201206': attribute('IS', 1),
        '00201208': attribute('IS', len(instances)),
    }


def series_record():
    return {
        '0020000D': attribute('UI', study_uid),
        '0020000E': attribute('UI', series_uid),
        '00080060': attribute('CS', 'CT'),
        '0008103E': attribute('LO', 'DICOMweb retrieved'),
        '00200011': attribute('IS', 1),
        '00201209': attribute('IS', len(instances)),
    }


def instance_records():
    return [{
        '0020000D': attribute('UI', study_uid),
        '0020000E': attribute('UI', series_uid),
        '00080018': attribute('UI', item['sop']),
        '00080016': attribute('UI', CTImageStorage),
        '00200013': attribute('IS', item['number']),
        '00280010': attribute('US', args.rows),
        '00280011': attribute('US', args.columns),
    } for item in instances]


def write_record():
    with lock:
        record.write_text(json.dumps({
            'port': args.port, 'studyInstanceUID': study_uid, 'seriesInstanceUID': series_uid,
            'patientID': args.patient_id, 'patientName': args.patient_name,
            'instances': [{'sopInstanceUID': item['sop'], 'file': item['path'].name} for item in instances],
            'requests': served,
        }, indent=1) + '\n')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass

    def json(self, records):
        body = json.dumps(records).encode()
        if not records:
            self.send_response(204)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/dicom+json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def multipart(self, wanted):
        boundary = 'horos384boundary'
        body = bytearray()
        for item in wanted:
            body += ('--%s\r\nContent-Type: application/dicom\r\n\r\n' % boundary).encode()
            body += item['path'].read_bytes()
            body += b'\r\n'
        body += ('--%s--\r\n' % boundary).encode()
        self.send_response(200)
        self.send_header('Content-Type',
                         'multipart/related; type="application/dicom"; boundary=%s' % boundary)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(bytes(body))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.strip('/')
        query = parse_qs(parsed.query)
        offset = int(query.get('offset', ['0'])[0])
        with lock:
            served.append({'path': path, 'query': {k: v for k, v in query.items()},
                           'accept': self.headers.get('Accept', '')})
        # Record as it happens: a record that needs a clean shutdown is a record
        # that can be lost.
        write_record()
        wado = 'multipart/related' in (self.headers.get('Accept') or '')

        if path == 'studies' and not wado:
            return self.json([] if offset else [study_record()])
        if re.fullmatch(r'studies/[0-9.]+/series', path) and not wado:
            return self.json([] if offset else [series_record()])
        if re.fullmatch(r'studies/[0-9.]+/series/[0-9.]+/instances', path) and not wado:
            return self.json([] if offset else instance_records())
        if re.fullmatch(r'studies/%s' % re.escape(study_uid), path) and wado:
            return self.multipart(instances)
        if re.fullmatch(r'studies/%s/series/%s' % (re.escape(study_uid), re.escape(series_uid)), path) and wado:
            return self.multipart(instances)
        self.send_response(404)
        self.send_header('Content-Length', '0')
        self.end_headers()


server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
record = args.evidence / 'dicomweb-fixture.json'


def stop(*_):
    write_record()
    threading.Thread(target=server.shutdown, daemon=True).start()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
write_record()
print(json.dumps({'port': args.port, 'studyInstanceUID': study_uid, 'seriesInstanceUID': series_uid,
                  'instances': len(instances), 'record': str(record)}))
try:
    server.serve_forever()
finally:
    write_record()
