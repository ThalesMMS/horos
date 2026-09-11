#!/usr/bin/env python3
"""A mammography study carrying Hardcopy objects among its images.

The report is of a study whose series holds an object of modality HC that brings
the application down when it is selected. Hardcopy Grayscale Image Storage is a
retired SOP class for what a printer produced, and the objects that turn up under
it in practice are not all images: some carry no Pixel Data at all, some declare
a size and carry none, and some are ordinary images that happen to be labelled
HC. All three are here, in one series with two real MG images, so a viewer that
refuses the object can still be told from one that refuses the series.

  mg-1, mg-2       ordinary MG images, the control
  hc-no-pixels     modality HC, no Pixel Data element at all
  hc-empty-pixels  modality HC, 512x512 declared, Pixel Data of zero length
  hc-image         modality HC carrying a real 512x512 image
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

HARDCOPY_GRAYSCALE = '1.2.840.10008.5.1.1.29'
DIGITAL_MAMMOGRAPHY_X_RAY = '1.2.840.10008.5.1.4.1.1.1.2'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
parser.add_argument('--size', type=int, default=512)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
study = generate_uid()
series = generate_uid()


def build(name, instance_number, sop_class, modality, pixels, declare_shape=True):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = sop_class
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = series
    dataset.PatientName = 'HARDCOPY^SERIES'
    dataset.PatientID = 'HARDCOPY-106'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'F'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'HC106'
    dataset.StudyID = '106'
    dataset.SeriesNumber = 1
    dataset.InstanceNumber = instance_number
    dataset.Modality = modality
    dataset.StudyDescription = 'Hardcopy among images'
    dataset.SeriesDescription = 'mammography with hardcopy'
    dataset.ImageType = ['DERIVED', 'SECONDARY'] if modality == 'HC' else ['ORIGINAL', 'PRIMARY']

    if declare_shape:
        dataset.Rows = size
        dataset.Columns = size
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = 'MONOCHROME2'
        dataset.BitsAllocated = 16
        dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 0
        dataset.WindowCenter = 2048.0
        dataset.WindowWidth = 4096.0
        dataset.PixelSpacing = [0.1, 0.1]

    if pixels is not None:
        dataset.PixelData = pixels

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-16s %-8s %s' % (name, modality,
                             'no Pixel Data' if pixels is None
                             else ('%d bytes' % len(pixels))))
    return path


def flat(value):
    """A uniform field, so which image is on screen is unmistakable."""
    return numpy.full((size, size), value, dtype=numpy.uint16).tobytes()


# Each image that has pixels is a different, uniform grey, so an object that
# shows another object's pixels is visible as such rather than as a picture.
build('mg-1', 1, DIGITAL_MAMMOGRAPHY_X_RAY, 'MG', flat(1000))
build('mg-2', 2, DIGITAL_MAMMOGRAPHY_X_RAY, 'MG', flat(3000))
# No shape and no pixels: the object is a hardcopy record, not a picture.
build('hc-no-pixels', 3, HARDCOPY_GRAYSCALE, 'HC', None, declare_shape=False)
build('hc-empty-pixels', 4, HARDCOPY_GRAYSCALE, 'HC', b'')
build('hc-image', 5, HARDCOPY_GRAYSCALE, 'HC', flat(2000))

print()
print('study %s' % study)
print('%d files in %s' % (len(list(arguments.destination.iterdir())), arguments.destination))
