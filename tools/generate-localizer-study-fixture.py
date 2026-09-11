#!/usr/bin/env python3
"""Generate a synthetic study with two localizer series and one ordinary series.

Horos groups the localizers of a study into one internal series when NOLOCALIZER
is set, which it is by default. This fixture is what that grouping is exercised
against: two real localizer series, so the merge has something to merge, and an
ordinary series beside them that must be left alone.
"""
import argparse
import json
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
parser.add_argument('--localizer-series', type=int, default=2)
parser.add_argument('--instances', type=int, default=2, help='instances per series')
args = parser.parse_args()
if not 1 <= args.localizer_series <= 10 or not 1 <= args.instances <= 50:
    parser.error('Keep the fixture small')
args.destination.mkdir(parents=True, exist_ok=True)
if any(args.destination.iterdir()):
    parser.error('Use an empty destination')

study = generate_uid()
manifest = {'study': study, 'localizer_series': [], 'other_series': [], 'instances': {}}


def write(series, series_number, description, image_type, count, name):
    for instance in range(1, count + 1):
        ds = Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = generate_uid()
        ds.StudyInstanceUID = study
        ds.SeriesInstanceUID = series
        ds.PatientName = 'QA^Localizer'
        ds.PatientID = 'LOCAL-LOCALIZER'
        ds.StudyDate = '20260909'
        ds.StudyTime = '120000'
        ds.StudyID = 'LOC'
        ds.StudyDescription = 'Synthetic localizer grouping'
        ds.SeriesDescription = description
        ds.SeriesNumber = series_number
        ds.InstanceNumber = instance
        ds.Modality = 'CT'
        ds.ImageType = list(image_type)
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
        ds.PixelData = b''.join(((series_number * 100 + instance + n) % 4096).to_bytes(2, 'little')
                                for n in range(256))
        path = args.destination / ('%s-%03d.dcm' % (name, instance))
        ds.save_as(path, enforce_file_format=True)
        manifest['instances'][str(ds.SOPInstanceUID)] = {'series': series, 'path': path.name}


for number in range(1, args.localizer_series + 1):
    series = generate_uid()
    manifest['localizer_series'].append(series)
    write(series, number, 'Scout %d' % number,
          ['DERIVED', 'SECONDARY', 'LOCALIZER'], args.instances, 'localizer%d' % number)

series = generate_uid()
manifest['other_series'].append(series)
write(series, args.localizer_series + 1, 'Axial', ['ORIGINAL', 'PRIMARY', 'AXIAL'],
      args.instances + 1, 'axial')

(args.destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('study %s' % study)
print('localizer series: %s' % ' '.join(manifest['localizer_series']))
print('other series: %s' % ' '.join(manifest['other_series']))
print('instances: %d' % len(manifest['instances']))
