#!/usr/bin/env python3
"""A long synthetic patient/study list for the browser table (#380, A300).

Writes `--patients` patients with `--studies` studies each and one 32x32 CT
image per study, so the browser's outline view has many consecutive rows of the
*same* patient — the condition under which it paints the name cell's background
(`displaySamePatientWithColorBackground`), which is what A300 is about.

    local-validation/venv/bin/python tools/generate-browser-list-fixture.py <empty dir>
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--patients', type=int, default=8)
parser.add_argument('--studies', type=int, default=6)
args = parser.parse_args()
if not 1 <= args.patients <= 200 or not 1 <= args.studies <= 50:
    parser.error('1-200 patients and 1-50 studies each')
out = args.output.resolve()
if out == root or root in out.parents:
    raise SystemExit('output must be outside the repository')
if out.exists() and any(out.iterdir()):
    raise SystemExit('output must be empty')
out.mkdir(parents=True, exist_ok=True)

pixels = np.zeros((32, 32), dtype='<i2')
pixels[8:24, 8:24] = 400
rows = []
for p in range(args.patients):
    name = 'BROWSER^LIST^%02d' % (p + 1)
    patient_id = 'SYNTHETIC-380-%02d' % (p + 1)
    for s in range(args.studies):
        study, series, sop = generate_uid(), generate_uid(), generate_uid()
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = sop
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        path = out / ('%02d-%02d.dcm' % (p + 1, s + 1))
        ds = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0' * 128)
        ds.SOPClassUID = CTImageStorage; ds.SOPInstanceUID = sop
        ds.StudyInstanceUID = study; ds.SeriesInstanceUID = series; ds.FrameOfReferenceUID = generate_uid()
        ds.PatientName = name; ds.PatientID = patient_id; ds.PatientBirthDate = '19700101'
        ds.StudyDate = '2026%02d%02d' % (1 + s % 12, 1 + p % 28); ds.StudyTime = '%02d0000' % (8 + s % 12)
        ds.Modality = 'CT'; ds.StudyDescription = 'Browser list study %d' % (s + 1)
        ds.SeriesDescription = 'Browser list series'; ds.SeriesNumber = 1; ds.InstanceNumber = 1
        ds.Rows = 32; ds.Columns = 32; ds.PixelSpacing = [1, 1]; ds.SliceThickness = 1
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]; ds.ImagePositionPatient = [-16, -16, 0]
        ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.BitsAllocated = 16; ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = 1
        ds.RescaleSlope = 1; ds.RescaleIntercept = 0; ds.WindowCenter = 200; ds.WindowWidth = 800
        ds.PixelData = pixels.tobytes()
        ds.save_as(path, enforce_file_format=True)
        rows.append({'patientID': patient_id, 'patientName': name, 'studyInstanceUID': study})
files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.dcm'))}
(out / 'manifest.json').write_text(json.dumps({'synthetic': True, 'patients': args.patients, 'studies': args.studies,
                                               'rows': rows, 'sha256': files}, indent=2) + '\n')
print(json.dumps({'output': str(out), 'patients': args.patients, 'studiesEach': args.studies, 'files': len(files)}))
