#!/usr/bin/env python3
"""Objects that are not pictures, or that keep their picture somewhere else.

A study can hold instances a viewer cannot display: a radiofluoroscopic object
whose main Pixel Data is absent but which carries an Icon Image Sequence, a
hardcopy object with no pixels at all sitting beside mammography images, an MR
spectroscopy object, and a private Siemens non-image object. What should happen
to each is the question; what must not happen is a picture being invented, or the
instance disappearing without a word.

    mg-normal        an ordinary mammography image, so the study has one
    rf-icon          RF with no Pixel Data and a 32x32 Icon Image Sequence
    hc-no-pixels     Hardcopy Grayscale, modality HC, no Pixel Data
    hc-with-pixels   Hardcopy Grayscale, modality HC, with a real picture
    spectroscopy     MR Spectroscopy Storage, which has no Pixel Data by design
    siemens-nonimage a private Siemens Non-Image Storage SOP class
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

DIGITAL_MAMMOGRAPHY = '1.2.840.10008.5.1.4.1.1.1.2'
RADIOFLUOROSCOPIC = '1.2.840.10008.5.1.4.1.1.12.2'
HARDCOPY_GRAYSCALE = '1.2.840.10008.5.1.1.29'
MR_SPECTROSCOPY = '1.2.840.10008.5.1.4.1.1.4.2'
SIEMENS_NON_IMAGE = '1.3.12.2.1107.5.9.1'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

study = generate_uid()


def common(name, series_number, description, sop_class, modality):
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
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'NONIMAGE^STUDY'
    dataset.PatientID = 'NONIMG-101'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'NONIMG101'
    dataset.StudyID = '101'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = modality
    dataset.StudyDescription = 'objects that are not pictures'
    dataset.SeriesDescription = description
    return dataset, instance


def image(dataset, rows, columns, values):
    dataset.Rows = rows
    dataset.Columns = columns
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.WindowCenter = 2000.0
    dataset.WindowWidth = 4000.0
    if values is not None:
        dataset.PixelData = values.tobytes()


def save(dataset, name, note):
    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-18s %-52s %s' % (name, dataset.SeriesDescription, note))


ramp = numpy.tile(numpy.linspace(0, 4000, 64), (64, 1)).astype(numpy.uint16)

dataset, _ = common('mg-normal', 1, 'an ordinary mammography image',
                    DIGITAL_MAMMOGRAPHY, 'MG')
image(dataset, 64, 64, ramp)
save(dataset, 'mg-normal', '64x64 with pixels')

# The picture is only in the icon: PS 3.3 C.7.6.1.1.6 says an Icon Image Sequence
# is a preview of the image, not the image.
dataset, _ = common('rf-icon', 2, 'RF whose only picture is its icon',
                    RADIOFLUOROSCOPIC, 'RF')
image(dataset, 1024, 1024, None)
icon = Dataset()
icon.Rows = 32
icon.Columns = 32
icon.SamplesPerPixel = 1
icon.PhotometricInterpretation = 'MONOCHROME2'
icon.BitsAllocated = 8
icon.BitsStored = 8
icon.HighBit = 7
icon.PixelRepresentation = 0
icon.PixelData = numpy.tile(numpy.linspace(0, 255, 32), (32, 1)).astype(numpy.uint8).tobytes()
dataset.IconImageSequence = [icon]
save(dataset, 'rf-icon', '1024x1024 declared, no Pixel Data, a 32x32 icon')

dataset, _ = common('hc-no-pixels', 3, 'hardcopy grayscale with no pixels',
                    HARDCOPY_GRAYSCALE, 'HC')
image(dataset, 2048, 2048, None)
save(dataset, 'hc-no-pixels', '2048x2048 declared, no Pixel Data')

# Not every hardcopy object is an empty white page: the class is a picture class,
# and one carrying pixels has to be shown as the picture it is.
dataset, _ = common('hc-with-pixels', 6, 'hardcopy grayscale with a picture',
                    HARDCOPY_GRAYSCALE, 'HC')
image(dataset, 64, 64, ramp[::-1].copy())
save(dataset, 'hc-with-pixels', '64x64 with pixels')

dataset, _ = common('spectroscopy', 4, 'MR spectroscopy', MR_SPECTROSCOPY, 'MR')
dataset.DataPointRows = 1
dataset.DataPointColumns = 512
dataset.NumberOfFrames = 1
dataset.SpectroscopyData = numpy.zeros(1024, dtype=numpy.float32).tobytes()
save(dataset, 'spectroscopy', 'no Pixel Data by design; 512 data points')

dataset, _ = common('siemens-nonimage', 5, 'a private Siemens non-image object',
                    SIEMENS_NON_IMAGE, 'OT')
dataset.SeriesDescription = 'a private Siemens non-image object'
save(dataset, 'siemens-nonimage', 'a private SOP class, no pixels of any kind')

print()
print('study %s' % study)
