#!/usr/bin/env python3
"""Two patients with the same name and different identifiers.

A list of medical record numbers is only safe to run unattended if resolving it
never merges two people. The case that catches a resolver that works by name is
two patients called the same thing, so this writes exactly that: `SILVA^MARIA`
twice, under `MRN-158-A` and `MRN-158-B`, with the first carrying two studies and
the second one. A resolver that goes by name gives three studies for either
identifier; one that goes by identifier gives two and one.

Every value here is written by this file; nothing comes from a person.

    python3 tools/generate-homonym-fixture.py <empty dir>
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
arguments = parser.parse_args()
arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

SIZE = 32


def write(name, patient_id, description, value):
    sop = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = sop
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = sop
    dataset.StudyInstanceUID = generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'SILVA^MARIA'          # the same for both patients
    dataset.PatientID = patient_id               # and this is what tells them apart
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'F'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.StudyID = '158'
    dataset.SeriesNumber = 1
    dataset.InstanceNumber = 1
    dataset.Modality = 'CT'
    dataset.StudyDescription = description
    dataset.SeriesDescription = name
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    dataset.ImagePositionPatient = [0.0, 0.0, 0.0]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.PixelSpacing = [1.0, 1.0]
    dataset.SliceThickness = 1.0
    dataset.Rows = SIZE
    dataset.Columns = SIZE
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.WindowCenter = 1000.0
    dataset.WindowWidth = 2000.0
    # A different constant per study, so a file copied under the wrong identifier
    # shows up as a different digest rather than as nothing.
    dataset.PixelData = numpy.full((SIZE, SIZE), value, dtype=numpy.uint16).tobytes()
    dataset.save_as(str(arguments.destination / ('%s.dcm' % name)), enforce_file_format=True)
    print('%-12s %-12s %s' % (name, patient_id, description))


write('a-first', 'MRN-158-A', 'first study of the first Maria Silva', 100)
write('a-second', 'MRN-158-A', 'second study of the first Maria Silva', 200)
write('b-only', 'MRN-158-B', 'the only study of the second Maria Silva', 300)
print('two patients named SILVA^MARIA: MRN-158-A has two studies, MRN-158-B has one')
