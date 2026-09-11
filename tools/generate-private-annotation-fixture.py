#!/usr/bin/env python3
"""An image carrying a private block, for the custom image annotations.

A custom annotation can name any group and element, including a private one.
`(0011,1005)` is the tag from the report; a private element is only meaningful
under its private creator, which reserves the block `(0011,10xx)` in
`(0011,0010)`. So the file carries:

    (0011,0010) LO  HOROS PRIVATE TEST     the private creator, block 0x10
    (0011,1005) LO  private annotation     the value the annotation asks for
    (0011,1006) DS  42.5                   a second one, to catch an off-by-one
    (0013,1005) LO  other block            the same element under another group
    (0010,0010) PN  PRIVATE^ANNOTATION     the patient name, for the placeholder

Nothing in the file needs a private dictionary to be read: the value is there
under its own tag, whatever name a dictionary would give it.
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the file')
parser.add_argument('--size', type=int, default=64)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
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
dataset.StudyInstanceUID = generate_uid()
dataset.SeriesInstanceUID = generate_uid()
dataset.PatientName = 'PRIVATE^ANNOTATION'
dataset.PatientID = 'PRIVATE-114'
dataset.PatientBirthDate = '19700101'
dataset.PatientSex = 'O'
dataset.StudyDate = '20260101'
dataset.StudyTime = '120000'
dataset.ContentDate = '20260101'
dataset.ContentTime = '120000'
dataset.AccessionNumber = 'PRIV114'
dataset.StudyID = '114'
dataset.SeriesNumber = 1
dataset.InstanceNumber = 1
dataset.Modality = 'CT'
dataset.StudyDescription = 'Private annotation'
dataset.SeriesDescription = 'private block'
dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
dataset.ImagePositionPatient = [0.0, 0.0, 0.0]
dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
dataset.PixelSpacing = [0.5, 0.5]
dataset.SliceThickness = 1.0
dataset.RepetitionTime = '250'
dataset.EchoTime = '12.5'

# The private creator reserves (0011,1000)-(0011,10ff) for itself.
dataset.add_new((0x0011, 0x0010), 'LO', 'HOROS PRIVATE TEST')
dataset.add_new((0x0011, 0x1005), 'LO', 'private annotation')
dataset.add_new((0x0011, 0x1006), 'DS', '42.5')
# A second private group, same element, to catch a lookup that ignores the group.
dataset.add_new((0x0013, 0x0010), 'LO', 'HOROS OTHER BLOCK')
dataset.add_new((0x0013, 0x1005), 'LO', 'other block')

dataset.Rows = size
dataset.Columns = size
dataset.SamplesPerPixel = 1
dataset.PhotometricInterpretation = 'MONOCHROME2'
dataset.BitsAllocated = 16
dataset.BitsStored = 16
dataset.HighBit = 15
dataset.PixelRepresentation = 0
dataset.RescaleIntercept = 0.0
dataset.RescaleSlope = 1.0
dataset.WindowCenter = 2000.0
dataset.WindowWidth = 4000.0
line = numpy.linspace(0, 4000, size)
dataset.PixelData = numpy.tile(line, (size, 1)).astype(numpy.uint16).tobytes()

path = arguments.destination / 'private-annotation.dcm'
dataset.save_as(str(path), enforce_file_format=True)

print(path)
for tag, name in (((0x0011, 0x0010), 'private creator'),
                  ((0x0011, 0x1005), 'private annotation'),
                  ((0x0011, 0x1006), 'private number'),
                  ((0x0013, 0x0010), 'other creator'),
                  ((0x0013, 0x1005), 'other block'),
                  ((0x0010, 0x0010), 'patient name')):
    element = dataset[tag]
    print('  (%04x,%04x) %-3s %-20s %s' % (tag[0], tag[1], element.VR, name, element.value))
