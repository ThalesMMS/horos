#!/usr/bin/env python3
"""Two studies whose metadata breaks a naive spreadsheet export.

A metadata export is only worth anything if it survives the values people
actually have. These two are written to break the three ways it goes wrong:

    quoted   ISO_IR 100. The study description holds a comma, a pair of double
             quotes and a carriage return; the institution holds a tab. A
             tab-separated file with no escaping turns any of those into extra
             columns or an extra row.
    unicode  ISO_IR 192. The patient's name is in UTF-8, with accents and CJK,
             and the study carries no Accession Number and no Institution Name,
             so a row has fields that are genuinely absent rather than empty.

Two patients, so a row that mixed them would be visible: every field of a row
has to come from that row's own study.

    python3 tools/generate-metadata-csv-fixture.py <empty dir>
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
picture = numpy.full((SIZE, SIZE), 1000, dtype=numpy.uint16).tobytes()


def write(name, charset, patient_name, patient_id, description, institution, accession):
    sop = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = sop
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = charset
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = sop
    dataset.StudyInstanceUID = generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = patient_name
    dataset.PatientID = patient_id
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.StudyID = '146'
    dataset.SeriesNumber = 1
    dataset.InstanceNumber = 1
    dataset.Modality = 'CT'
    dataset.StudyDescription = description
    dataset.SeriesDescription = name
    if institution is not None:
        dataset.InstitutionName = institution
    if accession is not None:
        dataset.AccessionNumber = accession
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
    dataset.PixelData = picture
    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-9s %-11s %s' % (name, charset, patient_id))
    return path


# A comma, a pair of quotes and a carriage return in one description, and a tab
# in the institution: the four characters a CSV has to quote or escape.
write('quoted', 'ISO_IR 100', 'QUOTED^COMMA', 'CSV-146-A',
      'Thorax, with contrast: he said "twice"\r and again',
      'Hospital\tof Tabs', 'ACC,146')

# Accents and CJK, declared as UTF-8, and two fields deliberately absent.
write('unicode', 'ISO_IR 192', 'Grüße^Jörg=グリュース^ヨルク', 'CSV-146-B',
      'Ressonância magnética — crânio', None, None)

print('two studies, two patients; the second has no AccessionNumber and no InstitutionName')
