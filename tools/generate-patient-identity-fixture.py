#!/usr/bin/env python3
"""Batches of one study whose patient identity agrees, or does not, and how.

The importer matches a study on the Study Instance UID together with a key built
from the patient's name, identifier and date of birth. This writes one study's
instances in batches that differ in exactly one of those, so that "the same
patient split in two" can be told apart from "two patients that really differ":

  same        two instances, name DOE^JOHN, id P66, born 19800101
  samelater   two more, identical in all three
  nodob       two more, identical except that they carry no date of birth
  otherid     one more, identical except that the identifier is P67
  othername   one more, identical except that the name is DOE^JANE

Every batch is in the same study, so a batch that lands in a study of its own
landed there because of the identity key and nothing else.
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
arguments = parser.parse_args()
arguments.destination.mkdir(parents=True, exist_ok=True)

STUDY = generate_uid()
NAME = 'DOE^JOHN'
IDENTIFIER = 'P66'
BIRTH = '19800101'


def write(batch, number, series, birth=BIRTH, name=NAME, identifier=IDENTIFIER):
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = dataset.file_meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = STUDY
    dataset.SeriesInstanceUID = series
    dataset.PatientName = name
    dataset.PatientID = identifier
    if birth is not None:
        dataset.PatientBirthDate = birth
    dataset.StudyDescription = 'Patient identity fixture'
    dataset.SeriesDescription = 'batch %s' % batch
    dataset.Modality = 'CT'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.SeriesNumber = number
    dataset.InstanceNumber = number
    dataset.Rows = dataset.Columns = 16
    dataset.BitsAllocated = dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.PixelData = numpy.full((16, 16), number * 10, dtype=numpy.uint16).tobytes()
    dataset.save_as(arguments.destination / ('%s-%d.dcm' % (batch, number)), enforce_file_format=True)


batches = [
    ('same', [1, 2], {}),
    ('samelater', [3, 4], {}),
    ('nodob', [5, 6], {'birth': None}),
    ('otherid', [7], {'identifier': 'P67'}),
    ('othername', [8], {'name': 'DOE^JANE'}),
]
for batch, numbers, changes in batches:
    series = generate_uid()
    for number in numbers:
        write(batch, number, series, **changes)

print('study %s' % STUDY)
print('patient %s / %s born %s' % (NAME, IDENTIFIER, BIRTH))
for batch, numbers, changes in batches:
    print('  %-10s %d instance(s)%s' % (batch, len(numbers),
                                        '' if not changes else ' — ' + ', '.join(
                                            '%s=%s' % (k, v) for k, v in changes.items())))
