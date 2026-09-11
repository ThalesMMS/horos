#!/usr/bin/env python3
"""Generate the archives an import folder has to have an answer for.

Three of them, because the interesting cases are not the one that works:

  - ``no-dicom.zip`` expands cleanly and holds nothing this database can index;
  - ``mixed.zip`` holds two instances of one series next to two files that are
    not DICOM at all;
  - ``corrupt.zip`` is named like an archive and is not one, so expanding it
    fails outright.

Synthetic throughout: the instances are generated here, so the archives can be
regenerated on any machine and carry no patient data.
"""
import argparse
import zipfile
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
parser.add_argument('--instances', type=int, default=2, help='DICOM instances inside mixed.zip')
arguments = parser.parse_args()

destination = arguments.destination
destination.mkdir(parents=True, exist_ok=True)

study = generate_uid()
series = generate_uid()


def instance(number: int) -> bytes:
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = dataset.file_meta.MediaStorageSOPInstanceUID
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = series
    dataset.PatientName = 'ARCHIVE^FIXTURE'
    dataset.PatientID = 'ARCHIVE-346'
    dataset.StudyDescription = 'Archive import fixture'
    dataset.SeriesDescription = 'Synthetic CT'
    dataset.Modality = 'CT'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.SeriesNumber = 1
    dataset.InstanceNumber = number
    dataset.Rows = dataset.Columns = 16
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    pixels = numpy.full((16, 16), number * 100, dtype=numpy.uint16)
    dataset.PixelData = pixels.tobytes()
    written = destination / ('instance-%d.dcm' % number)
    dataset.save_as(written, enforce_file_format=True)
    payload = written.read_bytes()
    written.unlink()
    return payload


NOTES = b'This file is not DICOM and never was.\n'
PICTURE = b'\x89PNG\r\n\x1a\n' + b'\x00' * 512

with zipfile.ZipFile(destination / 'no-dicom.zip', 'w') as archive:
    archive.writestr('readme.txt', NOTES)
    archive.writestr('notes/second.txt', NOTES)
    archive.writestr('picture.png', PICTURE)

with zipfile.ZipFile(destination / 'mixed.zip', 'w') as archive:
    for number in range(1, arguments.instances + 1):
        archive.writestr('images/instance-%d.dcm' % number, instance(number))
    archive.writestr('readme.txt', NOTES)
    archive.writestr('picture.png', PICTURE)

# Named like an archive, and unzip refuses it: no central directory at all.
(destination / 'corrupt.zip').write_bytes(b'PK\x03\x04' + b'\xde\xad\xbe\xef' * 64)

print('study %s' % study)
print('series %s' % series)
for archive in sorted(destination.glob('*.zip')):
    print('%-14s %7d bytes' % (archive.name, archive.stat().st_size))
