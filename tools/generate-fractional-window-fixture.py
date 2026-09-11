#!/usr/bin/env python3
"""Images whose stored window is narrower than one unit.

Rescale turns the stored integers into a small floating range, so the window
that shows the picture is fractional: WindowCenter 0.5 with WindowWidth 1 over
values from 0 to 1. Every field that shows or reads a window has to carry the
fraction, and an application that rounds it to integers windows the image at
level 0 width 1 instead, which is a different picture.

  narrow       WindowCenter 0.5, WindowWidth 1
  narrower     WindowCenter 0.25, WindowWidth 0.5
  ordinary     the control: a CT window, 40 / 400, over the same geometry
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

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


def ramp(dtype=numpy.uint16, high=1000):
    """A left-to-right ramp, the same in every row."""
    line = numpy.linspace(0, high, columns)
    return numpy.tile(line, (rows, 1)).astype(dtype)


def build(name, series_number, description, center, width, slope, intercept):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'WINDOW^FRACTIONAL'
    dataset.PatientID = 'WINDOW-105'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'WINDOW105'
    dataset.StudyID = '105'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'CT'
    dataset.StudyDescription = 'Fractional window'
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
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.RescaleIntercept = intercept
    dataset.RescaleSlope = slope
    dataset.RescaleType = 'US'
    dataset.WindowCenter = center
    dataset.WindowWidth = width
    dataset.PixelData = ramp().tobytes()

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-10s WindowCenter %-8s WindowWidth %-8s slope %-8s %s'
          % (name, center, width, slope, path.name))


# 0 … 1000 stored, slope 0.001, so the displayed values run 0 … 1.
build('narrow', 1, 'window 0.5 / 1', 0.5, 1.0, 0.001, 0.0)
build('narrower', 2, 'window 0.25 / 0.5', 0.25, 0.5, 0.0005, 0.0)
build('ordinary', 3, 'control: window 40 / 400', 40.0, 400.0, 1.0, -1024.0)

print()
print('study %s' % study)
print('%d files in %s' % (len(list(arguments.destination.iterdir())), arguments.destination))
