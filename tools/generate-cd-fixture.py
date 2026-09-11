#!/usr/bin/env python3
"""Generate a synthetic patient CD: several modalities, one file-set, a manifest.

A CD arrives as a DICOMDIR file-set holding a study's worth of series, often of
more than one modality. This builds one, and writes down every SOP Instance UID
with its modality and series, so what is on the disc can be compared against what
reached the database and what reached a destination node.
"""
import argparse
import json
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.fileset import FileSet
from pydicom.uid import (ComputedRadiographyImageStorage, CTImageStorage,
                         ExplicitVRLittleEndian, MRImageStorage, generate_uid)

STORAGE = {'CT': CTImageStorage, 'MR': MRImageStorage, 'CR': ComputedRadiographyImageStorage}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
parser.add_argument('--modalities', default='CT,MR,CR',
                    help='comma separated, one series each (default CT,MR,CR)')
parser.add_argument('--instances', type=int, default=4, help='instances per series')
parser.add_argument('--patient-id', default='LOCAL-CD')
args = parser.parse_args()
modalities = [m.strip().upper() for m in args.modalities.split(',') if m.strip()]
if not modalities or any(m not in STORAGE for m in modalities):
    parser.error('Modalities must be among %s' % ', '.join(sorted(STORAGE)))
if not 1 <= args.instances <= 50:
    parser.error('Keep the fixture small')
args.destination.mkdir(parents=True, exist_ok=True)
if any(args.destination.iterdir()):
    parser.error('Use an empty destination')

study = generate_uid()
manifest = {'study': study, 'patient_id': args.patient_id, 'instances': {}, 'series': {}}
media = FileSet()
media.ID = 'HOROS_QA_CD'
staging = args.destination / 'source'
staging.mkdir()

for number, modality in enumerate(modalities, start=1):
    series = generate_uid()
    manifest['series'][series] = modality
    for instance in range(1, args.instances + 1):
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPClassUID = STORAGE[modality]
        ds.SOPInstanceUID = generate_uid()
        ds.StudyInstanceUID = study
        ds.SeriesInstanceUID = series
        ds.PatientName = 'QA^CD'
        ds.PatientID = args.patient_id
        ds.PatientBirthDate = '19700101'
        ds.StudyDate = '20260909'
        ds.StudyTime = '120000'
        ds.StudyID = 'CD'
        ds.StudyDescription = 'Synthetic patient CD'
        ds.SeriesDescription = '%s series' % modality
        ds.SeriesNumber = number
        ds.InstanceNumber = instance
        ds.Modality = modality
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
        ds.PixelData = b''.join(((number * 1000 + instance + n) % 4096).to_bytes(2, 'little')
                                for n in range(256))
        path = staging / ('%s-%03d.dcm' % (modality.lower(), instance))
        ds.save_as(path, enforce_file_format=True)
        media.add(path)
        manifest['instances'][str(ds.SOPInstanceUID)] = {'modality': modality,
                                                         'series': series}

media.write(args.destination / 'disc')
(args.destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
written = len(FileSet(args.destination / 'disc' / 'DICOMDIR'))
assert written == len(manifest['instances']), (written, len(manifest['instances']))
print('study %s' % study)
print('series: %s' % ', '.join('%s (%s)' % (uid[-8:], m) for uid, m in manifest['series'].items()))
print('instances: %d in the DICOMDIR at %s' % (written, args.destination / 'disc'))
