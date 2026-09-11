#!/usr/bin/env python3
"""Serve what a URL import can be handed, none of it named by its extension.

Horos's "Import URL…" writes whatever comes back as a `.dcm` in the database
folder. This server exists to say what actually came back:

  /instance   a DICOM object            (200, application/dicom)
  /archive    a zip holding two of them (200, application/zip)
  /page       an HTML login page        (200, text/html) - what a proxy answers
  /missing    an error page             (404, text/html)

No path carries a file extension, which is the case the importer has to work out
for itself.
"""
import argparse
import io
import json
import zipfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=11190)
parser.add_argument('--record', type=Path, help='write a JSON log of the requests served')
arguments = parser.parse_args()

STUDY = generate_uid()
SERIES = generate_uid()


def instance(number: int) -> bytes:
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = dataset.file_meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = STUDY
    dataset.SeriesInstanceUID = SERIES
    dataset.PatientName = 'URLIMPORT^FIXTURE'
    dataset.PatientID = 'URL-69'
    dataset.StudyDescription = 'URL import fixture'
    dataset.SeriesDescription = 'Synthetic CT'
    dataset.Modality = 'CT'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.SeriesNumber = 1
    dataset.InstanceNumber = number
    dataset.Rows = dataset.Columns = 16
    dataset.BitsAllocated = dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.PixelData = numpy.full((16, 16), number * 100, dtype=numpy.uint16).tobytes()
    buffer = io.BytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


INSTANCE = instance(1)
ARCHIVE = io.BytesIO()
with zipfile.ZipFile(ARCHIVE, 'w') as archive:
    archive.writestr('images/instance-2.dcm', instance(2))
    archive.writestr('images/instance-3.dcm', instance(3))
ARCHIVE = ARCHIVE.getvalue()
PAGE = b'<html><head><title>Sign in</title></head><body>Please sign in.</body></html>'

served = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def answer(self, status, content_type, body):
        served.append({'path': self.path, 'status': status, 'bytes': len(body)})
        print('%s -> %d, %d bytes' % (self.path, status, len(body)), flush=True)
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = self.path.split('?')[0]
        print('request %.3f %s' % (time.monotonic(), route), flush=True)
        if route == '/never':
            time.sleep(90)
            return
        if route == '/slow':
            time.sleep(3)
            self.answer(200, 'application/dicom', instance(4))
            return
        if route == '/instance':
            self.answer(200, 'application/dicom', INSTANCE)
        elif route == '/archive':
            self.answer(200, 'application/zip', ARCHIVE)
        elif route == '/page':
            self.answer(200, 'text/html', PAGE)
        else:
            self.answer(404, 'text/html', b'<html><body>Not found</body></html>')


server = ThreadingHTTPServer(('127.0.0.1', arguments.port), Handler)
print('study %s' % STUDY)
print('series %s' % SERIES)
print('instance %d bytes, archive %d bytes' % (len(INSTANCE), len(ARCHIVE)))
print('serving on http://127.0.0.1:%d/{instance,archive,page,missing}' % arguments.port, flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    if arguments.record:
        arguments.record.write_text(json.dumps(served, indent=2))
