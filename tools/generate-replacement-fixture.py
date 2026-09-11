#!/usr/bin/env python3
"""Synthetic series whose files are later replaced in place, keeping their UIDs (#603).

`v1/` is the series as first imported: three 32×32 CT slices, every sample 100
(+ a marker pixel at the centre, 150). Every `v2-*` directory carries the
**same Study, Series and SOP Instance UIDs and the same file names** as `v1/`,
so copying a `v2-*` file over the database path of its `v1` twin is exactly the
"same path, same identifiers, different content" case the acceptance asks for:

    v2-pixels      same geometry, every sample 200 (marker 250)
    v2-dimensions  48×48 instead of 32×32, samples 200
    v2-geometry    same size, position shifted by 10 mm and a coronal orientation
    v2-rescale     same stored values as v2-pixels, RescaleIntercept -1000 (so HU differ)
    v2-multiframe  one file (the first), 3 frames, samples 200

Nothing here is a patient. Do not commit the output.

    local-validation/venv/bin/python tools/generate-replacement-fixture.py <empty dir>
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--slices', type=int, default=3)
arguments = parser.parse_args()
arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

STUDY = generate_uid()
SERIES = generate_uid()
SOPS = [generate_uid() for _ in range(arguments.slices)]
AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
CORONAL = [1.0, 0.0, 0.0, 0.0, 0.0, -1.0]


def dataset(index, *, size, value, marker, orientation, origin, intercept, frames=1):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = SOPS[index]
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.ImplementationClassUID = generate_uid()
    ds.SpecificCharacterSet = 'ISO_IR 100'
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = SOPS[index]
    ds.StudyInstanceUID = STUDY
    ds.SeriesInstanceUID = SERIES
    ds.PatientName = 'LOCAL^REPLACE-603'
    ds.PatientID = 'REPLACE-603'
    ds.PatientBirthDate = '19700101'
    ds.PatientSex = 'O'
    ds.StudyDate = ds.ContentDate = '20260914'
    ds.StudyTime = ds.ContentTime = '120000'
    ds.AccessionNumber = 'R603'
    ds.StudyID = '603'
    ds.SeriesNumber = 1
    ds.InstanceNumber = index + 1
    ds.Modality = 'CT'
    ds.StudyDescription = 'synthetic file replacement fixture'
    ds.SeriesDescription = 'Replace 603'
    ds.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    ds.ImagePositionPatient = [origin[0], origin[1], origin[2] + float(index)]
    ds.ImageOrientationPatient = orientation
    ds.SliceLocation = origin[2] + float(index)
    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = 1.0
    ds.SpacingBetweenSlices = 1.0
    ds.RescaleIntercept = float(intercept)
    ds.RescaleSlope = 1.0
    ds.RescaleType = 'HU'
    ds.Rows = ds.Columns = size
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    picture = numpy.full((size, size), value, dtype=numpy.uint16)
    picture[size // 2, size // 2] = marker
    if frames > 1:
        ds.NumberOfFrames = frames
        picture = numpy.stack([picture] * frames)
    ds.PixelData = picture.tobytes()
    return ds


def write(directory, variant, count=None):
    directory.mkdir()
    for index in range(count if count is not None else arguments.slices):
        ds = dataset(index, **variant)
        ds.save_as(str(directory / ('%02d.dcm' % (index + 1))), write_like_original=False)


base = dict(size=32, value=100, marker=150, orientation=AXIAL, origin=[0.0, 0.0, 0.0], intercept=0)
write(arguments.destination / 'v1', base)
write(arguments.destination / 'v2-pixels', dict(base, value=200, marker=250))
write(arguments.destination / 'v2-dimensions', dict(base, size=48, value=200, marker=250))
write(arguments.destination / 'v2-geometry', dict(base, value=200, marker=250, orientation=CORONAL, origin=[10.0, 10.0, 10.0]))
write(arguments.destination / 'v2-rescale', dict(base, value=200, marker=250, intercept=-1000))
write(arguments.destination / 'v2-multiframe', dict(base, value=200, marker=250, frames=3), count=1)

print('study             %s' % STUDY)
print('series            %s' % SERIES)
print('sops              %s' % ' '.join(SOPS))
print('v1                %d slices 32x32, samples 100, centre 150, axial at origin' % arguments.slices)
print('v2-pixels         samples 200, centre 250 (same geometry)')
print('v2-dimensions     48x48')
print('v2-geometry       coronal, origin (10,10,10)')
print('v2-rescale        intercept -1000')
print('v2-multiframe     01.dcm with 3 frames')
print('wrote             %s' % arguments.destination)
