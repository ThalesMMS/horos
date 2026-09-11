#!/usr/bin/env python3
"""Objects whose metadata is stored under the wrong value representation.

A DICOM parser gives back a value whose class follows the VR the file declares.
An application that expects a number and is handed bytes - because the file said
`OB` where the standard says `DS` - asks those bytes for a number, and in
Objective-C that is an unrecognised selector: the process dies naming nothing.

Each variant is a copy of the same small CT, with one group of attributes rewritten
under a VR that cannot hold what the reader wants:

    window-as-bytes      WindowCenter and WindowWidth as OB
    rescale-as-bytes     RescaleIntercept and RescaleSlope as OB
    spacing-as-bytes     PixelSpacing and SliceThickness as OB
    geometry-as-bytes    ImagePositionPatient and ImageOrientationPatient as OB
    bits-as-text         BitsAllocated, BitsStored and HighBit as LO text
    empty-numbers        the same numeric attributes present and empty
    control              nothing rewritten, so the study has one image that works
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

study = generate_uid()
ramp = numpy.tile(numpy.linspace(0, 4000, 64), (64, 1)).astype(numpy.uint16)

TAGS = {
    'window': [(0x0028, 0x1050), (0x0028, 0x1051)],
    'rescale': [(0x0028, 0x1052), (0x0028, 0x1053)],
    'spacing': [(0x0028, 0x0030), (0x0018, 0x0050)],
    'geometry': [(0x0020, 0x0032), (0x0020, 0x0037)],
    'bits': [(0x0028, 0x0100), (0x0028, 0x0101), (0x0028, 0x0102)],
}


def build(name, series_number, description, rewrite=(), vr='OB', value=b'\x01\x02\x03\x04',
          empty=()):
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
    dataset.PatientName = 'WRONGVR^TYPES'
    dataset.PatientID = 'WRONGVR-118'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'WRONGVR118'
    dataset.StudyID = '118'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'CT'
    dataset.StudyDescription = 'metadata under the wrong value representation'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']

    dataset.ImagePositionPatient = [0.0, 0.0, float(series_number)]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.PixelSpacing = [0.5, 0.5]
    dataset.SliceThickness = 1.0
    dataset.RescaleIntercept = -1024.0
    dataset.RescaleSlope = 1.0
    dataset.WindowCenter = 2000.0
    dataset.WindowWidth = 4000.0

    dataset.Rows = 64
    dataset.Columns = 64
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelData = ramp.tobytes()

    # The pixel data VR is chosen from BitsAllocated at write time, so it has to
    # be settled before that attribute is spoiled.
    dataset['PixelData'].VR = 'OW'

    for group in rewrite:
        for tag in TAGS[group]:
            dataset[tag] = DataElement(tag, vr, value)
    for group in empty:
        for tag in TAGS[group]:
            dataset[tag] = DataElement(tag, dataset[tag].VR, None)

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-18s %-52s %s' % (name, description, ', '.join(rewrite or empty) or 'nothing'))


build('control', 1, 'nothing rewritten')
build('window-as-bytes', 2, 'window centre and width as OB', rewrite=('window',))
build('rescale-as-bytes', 3, 'rescale intercept and slope as OB', rewrite=('rescale',))
build('spacing-as-bytes', 4, 'pixel spacing and slice thickness as OB', rewrite=('spacing',))
build('geometry-as-bytes', 5, 'position and orientation as OB', rewrite=('geometry',))
build('bits-as-text', 6, 'bits allocated, stored and high bit as text',
      rewrite=('bits',), vr='LO', value=b'sixteen ')
build('empty-numbers', 7, 'the numeric attributes present and empty',
      empty=('window', 'rescale', 'spacing', 'geometry'))

print()
print('study %s' % study)
