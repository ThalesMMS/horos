#!/usr/bin/env python3
"""The same Cyrillic name written four ways, one of them not conformant.

DICOM says which character set a file uses in Specific Character Set (0008,0005).
Equipment that predates that habit writes the bytes of whatever code page the
operating system had - in Russia, Windows-1251 - and says nothing. A reader that
falls back to Latin-1, which is what the standard's default amounts to, turns
those bytes into mojibake, and there is nothing in the file to tell it otherwise.

    iso-ir-144    Specific Character Set ISO_IR 144, bytes in ISO-8859-5
    utf-8         Specific Character Set ISO_IR 192, bytes in UTF-8
    cp1251-silent no Specific Character Set at all, bytes in Windows-1251
    cp1251-said   Specific Character Set "WINDOWS-1251", which is not a DICOM
                  term but is what some equipment writes
"""
import argparse
import json
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

study = generate_uid()
ramp = numpy.tile(numpy.linspace(0, 4000, 32), (32, 1)).astype(numpy.uint16)

NAME = 'Иванов^Иван'
DESCRIPTION = 'Голова'


def build(name, series_number, character_set, encoding):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    if character_set is not None:
        dataset.SpecificCharacterSet = character_set
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientID = 'CHARSET-90'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'CHARSET90'
    dataset.StudyID = '90'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'CT'
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    dataset.ImagePositionPatient = [0.0, 0.0, float(series_number)]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.PixelSpacing = [0.5, 0.5]
    dataset.SliceThickness = 1.0

    dataset.Rows = 32
    dataset.Columns = 32
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.WindowCenter = 2000.0
    dataset.WindowWidth = 4000.0
    # Written as raw bytes, because the point is which bytes are in the file.
    dataset.PatientName = NAME.encode(encoding)
    dataset.StudyDescription = DESCRIPTION.encode(encoding)
    dataset.SeriesDescription = ('%s %s' % (name, DESCRIPTION)).encode(encoding)
    dataset.PixelData = ramp.tobytes()
    dataset['PixelData'].VR = 'OW'

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-14s SpecificCharacterSet=%-14s bytes in %-12s %s'
          % (name, character_set if character_set is not None else '(absent)', encoding,
             dataset.PatientName))
    return {'name': name, 'series': '%s %s' % (name, DESCRIPTION),
            'characterSet': character_set, 'encoding': encoding,
            'patientName': NAME, 'studyDescription': DESCRIPTION}


variants = [
    build('iso-ir-144', 1, 'ISO_IR 144', 'iso-8859-5'),
    build('utf-8', 2, 'ISO_IR 192', 'utf-8'),
    build('cp1251-silent', 3, None, 'cp1251'),
    build('cp1251-said', 4, 'WINDOWS-1251', 'cp1251'),
]

(arguments.destination / 'expected.json').write_text(
    json.dumps(variants, indent=1, ensure_ascii=False))
print()
print('study %s' % study)
print('the name is %s and the study description is %s in every file' % (NAME, DESCRIPTION))
