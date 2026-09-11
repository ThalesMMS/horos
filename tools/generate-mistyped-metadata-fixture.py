#!/usr/bin/env python3
"""Images whose metadata is not the type the reader expects.

The reports carry `-[NSMutableData floatValue]` and `-[NSString initWithString:nil]`
in the log, from an attribute parsed as something other than what the ivar it is
assigned to was declared to be. A file can produce that by declaring a value
representation that does not match the element, which real equipment does.

    ob-numbers     RepetitionTime, EchoTime, FlipAngle as OB - raw bytes where
                   a decimal string belongs
    ob-strings     ViewPosition, PatientPosition, ImageLaterality as OB
    us-angles      PositionerPrimaryAngle and PositionerSecondaryAngle as US,
                   unsigned integers where a decimal string belongs
    empty-values   the same elements present and empty, which is legal
    good           the control: every element with the value representation it
                   should have

Every variant carries the same readable picture, so "the image still decoded" is
a question with an answer.
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
parser.add_argument('--size', type=int, default=64)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
study = generate_uid()
line = numpy.linspace(0, 2000, size)
picture = numpy.tile(line, (size, 1)).astype(numpy.uint16).tobytes()

# (keyword, tag, the value representation it should have)
ELEMENTS = [
    ('RepetitionTime', (0x0018, 0x0080), 'DS'),
    ('EchoTime', (0x0018, 0x0081), 'DS'),
    ('FlipAngle', (0x0018, 0x1314), 'DS'),
    ('ViewPosition', (0x0018, 0x5101), 'CS'),
    ('PatientPosition', (0x0018, 0x5100), 'CS'),
    ('ImageLaterality', (0x0020, 0x0062), 'CS'),
    ('PositionerPrimaryAngle', (0x0018, 0x1510), 'DS'),
    ('PositionerSecondaryAngle', (0x0018, 0x1511), 'DS'),
]

GOOD = {
    'RepetitionTime': '250', 'EchoTime': '12.5', 'FlipAngle': '90',
    'ViewPosition': 'AP', 'PatientPosition': 'HFS', 'ImageLaterality': 'L',
    'PositionerPrimaryAngle': '-30.5', 'PositionerSecondaryAngle': '12',
}


def build(name, series_number, description, rewrite):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = MRImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = MRImageStorage
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'MISTYPED^METADATA'
    dataset.PatientID = 'MISTYPED-118'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'MIS118'
    dataset.StudyID = '118'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'MR'
    dataset.StudyDescription = 'Mistyped metadata'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY']
    dataset.ImagePositionPatient = [0.0, 0.0, 0.0]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.PixelSpacing = [0.5, 0.5]
    dataset.SliceThickness = 1.0

    dataset.Rows = size
    dataset.Columns = size
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.WindowCenter = 1000.0
    dataset.WindowWidth = 2000.0
    dataset.PixelData = picture

    rewrite(dataset)

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    shown = []
    for keyword, tag, _ in ELEMENTS:
        if tag in dataset:
            element = dataset[tag]
            shown.append('%s %s' % (keyword, element.VR))
    print('%-14s %-44s %s' % (name, description, ', '.join(shown) or 'none'))


def good(dataset):
    for keyword, tag, vr in ELEMENTS:
        dataset.add_new(tag, vr, GOOD[keyword])


def as_bytes(keywords):
    def rewrite(dataset):
        good(dataset)
        for keyword, tag, _ in ELEMENTS:
            if keyword in keywords:
                del dataset[tag]
                # OB: the reader gets bytes where it expects a decimal string.
                dataset.add_new(tag, 'OB', GOOD[keyword].encode('ascii') + b'\x00')
    return rewrite


def as_unsigned(keywords):
    def rewrite(dataset):
        good(dataset)
        for keyword, tag, _ in ELEMENTS:
            if keyword in keywords:
                del dataset[tag]
                dataset.add_new(tag, 'US', 300)
    return rewrite


def empty(dataset):
    for keyword, tag, vr in ELEMENTS:
        dataset.add_new(tag, vr, None)


build('good', 1, 'every element with the right value representation', good)
build('ob-numbers', 2, 'RepetitionTime, EchoTime, FlipAngle as OB',
      as_bytes({'RepetitionTime', 'EchoTime', 'FlipAngle'}))
build('ob-strings', 3, 'ViewPosition, PatientPosition, ImageLaterality as OB',
      as_bytes({'ViewPosition', 'PatientPosition', 'ImageLaterality'}))
build('us-angles', 4, 'the positioner angles as US',
      as_unsigned({'PositionerPrimaryAngle', 'PositionerSecondaryAngle'}))
build('empty-values', 5, 'every element present and empty', empty)

print()
print('study %s' % study)
print('every variant carries the same %d x %d picture' % (size, size))
