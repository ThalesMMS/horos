#!/usr/bin/env python3
"""Generate a study whose instances fail a C-STORE in different ways.

One send, several outcomes: CT instances a node accepts, an ultrasound instance
for which it will offer no presentation context, and - written separately, since
no importer would take it - an instance whose dataset carries no SOP Class UID,
which is what makes a C-STORE fail with "inappropriate data for message".
"""
import argparse
import json
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (CTImageStorage, ExplicitVRLittleEndian, UltrasoundImageStorage,
                         generate_uid)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
parser.add_argument('--ct-instances', type=int, default=4)
parser.add_argument('--us-instances', type=int, default=2)
args = parser.parse_args()
if not 1 <= args.ct_instances <= 50 or not 0 <= args.us_instances <= 50:
    parser.error('Keep the fixture small')
args.destination.mkdir(parents=True, exist_ok=True)
if any(args.destination.iterdir()):
    parser.error('Use an empty destination')

study = generate_uid()
manifest = {'study': study, 'ct': [], 'us': [], 'without_sop_class': []}


def base(sop_class, series, number, modality):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = study
    ds.SeriesInstanceUID = series
    ds.PatientName = 'QA^Store'
    ds.PatientID = 'LOCAL-STORE'
    ds.StudyDate = '20260909'
    ds.StudyTime = '120000'
    ds.StudyID = 'STO'
    ds.StudyDescription = 'Synthetic C-STORE failures'
    ds.SeriesDescription = '%s series' % modality
    ds.SeriesNumber = 1 if modality == 'CT' else 2
    ds.InstanceNumber = number
    ds.Modality = modality
    ds.Rows = ds.Columns = 16
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelSpacing = [1, 1]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0, 0, number]
    ds.SliceThickness = 1
    ds.PixelData = b''.join(((number * 100 + n) % 4096).to_bytes(2, 'little') for n in range(256))
    return ds


ct_series = generate_uid()
for number in range(1, args.ct_instances + 1):
    ds = base(CTImageStorage, ct_series, number, 'CT')
    ds.save_as(args.destination / ('ct-%03d.dcm' % number), enforce_file_format=True)
    manifest['ct'].append(str(ds.SOPInstanceUID))

us_series = generate_uid()
for number in range(1, args.us_instances + 1):
    ds = base(UltrasoundImageStorage, us_series, number, 'US')
    ds.save_as(args.destination / ('us-%03d.dcm' % number), enforce_file_format=True)
    manifest['us'].append(str(ds.SOPInstanceUID))

# The dataset of this one has no SOP Class UID. The file meta header keeps one,
# so it is still a readable DICOM file - which is the point: the failure appears
# only when the sender looks for the identity it has to put in the C-STORE.
ds = base(CTImageStorage, ct_series, args.ct_instances + 1, 'CT')
manifest['without_sop_class'].append(str(ds.SOPInstanceUID))
# The meta header is filled in by hand, because pydicom copies it from the
# dataset and there will be nothing there to copy.
ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
del ds.SOPClassUID
ds.save_as(args.destination / 'without-sop-class.dcm', enforce_file_format=True)

(args.destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('study %s' % study)
print('ct: %d  us: %d  without SOP class: 1' % (len(manifest['ct']), len(manifest['us'])))
