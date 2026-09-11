#!/usr/bin/env python3
"""Images whose pixels are 32 bits wide, each in its own series.

Every variant carries the same picture - a horizontal ramp, left to right,
spanning the range its own type can hold - so the question "were the values
preserved?" has a shape as well as a number behind it. A reader that takes the
low half of each word, or reads the bytes as something they are not, does not
produce a ramp: it produces bands, or a flat field.

  16u          the control: BitsAllocated 16, unsigned, ramp 0 … 4000
  32u          BitsAllocated 32, unsigned, ramp 0 … 4000000
  32s          BitsAllocated 32, signed, ramp -2000000 … 2000000
  32u-slope    32-bit unsigned with RescaleSlope 2, which is the one path that
               already converted the words instead of reinterpreting them
  float        Float Pixel Data (7FE0,0008) and no Pixel Data at all

The 32-bit integer variants are CT Image Storage, which the standard says is 16
bits: they are what the reports describe, not what a validator would accept, and
that is the point of measuring them.
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (CTImageStorage, ExplicitVRLittleEndian,
                         SecondaryCaptureImageStorage, generate_uid)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
parser.add_argument('--rows', type=int, default=64)
parser.add_argument('--columns', type=int, default=64)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

study = generate_uid()
rows, columns = arguments.rows, arguments.columns


def ramp(low, high, dtype):
    """A left-to-right ramp from low to high, the same in every row."""
    line = numpy.linspace(low, high, columns)
    return numpy.tile(line, (rows, 1)).astype(dtype)


def build(name, series_number, description, sop_class, pixels, **attributes):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = sop_class
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'PIXELS^32BIT'
    dataset.PatientID = 'PIX32-100'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'PIX32100'
    dataset.StudyID = '100'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'CT' if sop_class == CTImageStorage else 'OT'
    dataset.StudyDescription = '32-bit pixel data'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    dataset.ImagePositionPatient = [0.0, 0.0, float(series_number)]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.PixelSpacing = [0.5, 0.5]
    dataset.SliceThickness = 1.0

    dataset.Rows = rows
    dataset.Columns = columns
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    for key, value in attributes.items():
        setattr(dataset, key, value)

    if pixels is not None:
        dataset.PixelData = pixels.tobytes()

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    low = pixels.min() if pixels is not None else None
    high = pixels.max() if pixels is not None else None
    print('%-10s %-46s %s' % (name, description, path.name))
    print('           %d bits, %s, ramp %s … %s'
          % (getattr(dataset, 'BitsAllocated', 32),
             'signed' if getattr(dataset, 'PixelRepresentation', 0) else 'unsigned',
             low, high))
    return dataset


build('16u', 1, 'control: 16-bit unsigned ramp', CTImageStorage,
      ramp(0, 4000, numpy.uint16),
      BitsAllocated=16, BitsStored=16, HighBit=15, PixelRepresentation=0,
      RescaleIntercept=0.0, RescaleSlope=1.0, WindowCenter=2000.0, WindowWidth=4000.0)

build('32u', 2, '32-bit unsigned ramp, no rescale', CTImageStorage,
      ramp(0, 4000000, numpy.uint32),
      BitsAllocated=32, BitsStored=32, HighBit=31, PixelRepresentation=0,
      RescaleIntercept=0.0, RescaleSlope=1.0,
      WindowCenter=2000000.0, WindowWidth=4000000.0)

build('32s', 3, '32-bit signed ramp, no rescale', CTImageStorage,
      ramp(-2000000, 2000000, numpy.int32),
      BitsAllocated=32, BitsStored=32, HighBit=31, PixelRepresentation=1,
      RescaleIntercept=0.0, RescaleSlope=1.0,
      WindowCenter=0.0, WindowWidth=4000000.0)

build('32u-slope', 4, '32-bit unsigned ramp with RescaleSlope 2', CTImageStorage,
      ramp(0, 2000000, numpy.uint32),
      BitsAllocated=32, BitsStored=32, HighBit=31, PixelRepresentation=0,
      RescaleIntercept=0.0, RescaleSlope=2.0,
      WindowCenter=2000000.0, WindowWidth=4000000.0)

# Float Pixel Data instead of Pixel Data: nothing in the reading path looks for
# (7FE0,0008), so this is the "format this application does not read" case.
floats = build('float', 5, 'Float Pixel Data (7FE0,0008), no Pixel Data',
               SecondaryCaptureImageStorage, None,
               BitsAllocated=32, BitsStored=32, HighBit=31, PixelRepresentation=0,
               WindowCenter=0.5, WindowWidth=1.0)
floats.FloatPixelData = ramp(0.0, 1.0, numpy.float32).tobytes()
floats.save_as(str(arguments.destination / 'float.dcm'), enforce_file_format=True)

print()
print('study %s' % study)
print('%d files in %s' % (len(list(arguments.destination.iterdir())), arguments.destination))
