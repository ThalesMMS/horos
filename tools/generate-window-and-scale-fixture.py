#!/usr/bin/env python3
"""Radiographs that come out flat, and radiographs that only look as if they do.

The reports are of an examination shown as one field of grey, or black, with no
dataset attached. Two very different things produce that picture: pixels that
never arrived, and pixels that arrived and are being windowed out of sight. This
writes both, and the shapes in between, so the two can be told apart:

    plain                 the control: 16-bit unsigned, window over the data
    window-above-range    the same pixels, Window Center 30000 Width 100
    window-zero-width     the same pixels, Window Width 0
    no-window-tags        the same pixels, no Window Center or Width at all
    stored-12-of-16       Bits Stored 12, samples inside 12 bits - a control
    stored-12-data-16     Bits Stored 12, samples filling 16 - the header lies
    signed-unsigned-data  Pixel Representation 1, samples above 32767
    rescale-negative      Rescale Slope -1, Intercept 4095 - the picture inverts
    voi-lut-flat          a VOI LUT Sequence that maps every value to one

Every instance carries the same picture: a ramp that brightens to the right,
with a bright square in the top-left corner. A viewer that reads the pixels but
windows them away is flat; one that misreads them is not flat, and is not this
either. Orientation is checkable from the square alone.

    python3 tools/generate-window-and-scale-fixture.py <empty dir> [--size 256]
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ComputedRadiographyImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--size', type=int, default=256)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
study = generate_uid()


def picture(top):
    """A ramp to the right, with a bright square in the top-left corner."""
    image = numpy.tile(numpy.linspace(0, top, size), (size, 1))
    corner = max(size // 8, 4)
    image[:corner, :corner] = top
    return image


def build(name, number, description, pixels, **overrides):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = ComputedRadiographyImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = ComputedRadiographyImageStorage
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'FLATFIELD^RADIOGRAPH'
    dataset.PatientID = 'FLAT-84'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'FLAT84'
    dataset.StudyID = '84'
    dataset.SeriesNumber = number
    dataset.InstanceNumber = 1
    dataset.Modality = 'CR'
    dataset.StudyDescription = 'a picture that is there, and a window that hides it'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY']
    dataset.PixelSpacing = [0.2, 0.2]

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
    for key, value in overrides.items():
        if value is None:
            if key in dataset:
                del dataset[key]
        else:
            setattr(dataset, key, value)

    dataset.PixelData = pixels.astype(
        numpy.int16 if dataset.PixelRepresentation else numpy.uint16).tobytes()

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-22s %-48s %s' % (name, description, path.name))


ramp = picture(4095)

build('plain', 1, 'a ramp with a bright corner, windowed over its own range', ramp)
build('window-above-range', 2, 'the same ramp, Window Center 30000 Width 100', ramp,
      WindowCenter=30000.0, WindowWidth=100.0)
build('window-zero-width', 3, 'the same ramp, Window Width 0', ramp,
      WindowCenter=2048.0, WindowWidth=0.0)
build('no-window-tags', 4, 'the same ramp, no Window Center or Width', ramp,
      WindowCenter=None, WindowWidth=None)
build('stored-12-of-16', 5, 'Bits Stored 12, samples inside 12 bits', ramp,
      BitsStored=12, HighBit=11)
build('stored-12-data-16', 6, 'Bits Stored 12, samples filling 16 bits', picture(65535),
      BitsStored=12, HighBit=11, WindowCenter=32768.0, WindowWidth=65536.0)
build('signed-unsigned-data', 7, 'Pixel Representation 1, samples above 32767',
      picture(65535) - 32768, PixelRepresentation=1,
      WindowCenter=0.0, WindowWidth=65536.0)
build('rescale-negative', 8, 'Rescale Slope -1, Intercept 4095', ramp,
      RescaleSlope=-1.0, RescaleIntercept=4095.0, RescaleType='US')

# A VOI LUT that answers the same value for every input: the pixels are there
# and every one of them is drawn the same, which is a flat field with a cause
# that is neither the pixels nor Window Center.
flat = Dataset()
flat.LUTDescriptor = [4096, 0, 16]
flat.LUTExplanation = 'every value maps to one'
flat.LUTData = (numpy.full(4096, 2048, dtype=numpy.uint16)).tobytes()
build('voi-lut-flat', 9, 'a VOI LUT Sequence that maps every value to one', ramp,
      VOILUTSequence=[flat], WindowCenter=None, WindowWidth=None)

print()
print('study %s' % study)
print('patient FLATFIELD^RADIOGRAPH / FLAT-84')
