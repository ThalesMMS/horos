#!/usr/bin/env python3
"""One series whose images each carry a different window, and one that does not.

Every image holds the same picture - a horizontal ramp over the same value
range - so what changes from image to image is only the window the file asks
for. An application that keeps each image's own default shows five visibly
different renderings while scrolling; one that carries the first image's window
along shows five identical ones.

  heterogeneous   five images, WindowCenter/WindowWidth 100/200, 300/200,
                  500/200, 700/200, 900/200
  uniform         the control: five images, all 500/1000

A second study repeats the heterogeneous series with a key image in each of two
different series, for the path that gathers key images from several series into
one viewer.
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

rows, columns = arguments.rows, arguments.columns
line = numpy.linspace(0, 1000, columns)
picture = numpy.tile(line, (rows, 1)).astype(numpy.uint16).tobytes()


def build(study, series, series_number, instance_number, description, centre, width,
          name, patient_id, study_id, folder):
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
    dataset.SeriesInstanceUID = series
    dataset.PatientName = name
    dataset.PatientID = patient_id
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = study_id
    dataset.StudyID = study_id
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = instance_number
    dataset.Modality = 'CT'
    dataset.StudyDescription = 'Heterogeneous window'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    dataset.ImagePositionPatient = [0.0, 0.0, float(instance_number)]
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
    dataset.RescaleIntercept = 0.0
    dataset.RescaleSlope = 1.0
    dataset.WindowCenter = float(centre)
    dataset.WindowWidth = float(width)
    dataset.PixelData = picture

    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('%s-%02d.dcm' % (description.replace(' ', '-'), instance_number))
    dataset.save_as(str(path), enforce_file_format=True)
    return path


windows = [(100, 200), (300, 200), (500, 200), (700, 200), (900, 200)]

study = generate_uid()
series = generate_uid()
for index, (centre, width) in enumerate(windows, start=1):
    build(study, series, 1, index, 'heterogeneous', centre, width,
          'WINDOW^HETEROGENEOUS', 'WINDOW-103', '103', arguments.destination)
uniform = generate_uid()
for index in range(1, len(windows) + 1):
    build(study, uniform, 2, index, 'uniform', 500, 1000,
          'WINDOW^HETEROGENEOUS', 'WINDOW-103', '103', arguments.destination)

# A second study whose two series carry different windows, for the viewer that
# gathers images from several series at once.
across = generate_uid()
for series_number, (centre, width) in enumerate(((100, 200), (900, 200)), start=1):
    series = generate_uid()
    for index in range(1, 3):
        build(across, series, series_number, index,
              'across %d' % series_number, centre, width,
              'WINDOW^ACROSSSERIES', 'WINDOW-103B', '103B', arguments.destination)

print('study %s: series heterogeneous (%s) and uniform'
      % (study, ', '.join('%d/%d' % w for w in windows)))
print('study %s: two series, 100/200 and 900/200' % across)
print('%d files in %s' % (len(list(arguments.destination.iterdir())), arguments.destination))
