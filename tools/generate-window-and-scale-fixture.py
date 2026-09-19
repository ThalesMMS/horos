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
from pydicom.uid import CTImageStorage, ComputedRadiographyImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--size', type=int, default=256)
parser.add_argument('--content-fit', action='store_true', help='generate a synthetic content auto-zoom series instead of the windowing matrix')
parser.add_argument('--curved-table', action='store_true', help='include a curved support below the synthetic content-fit body')
parser.add_argument('--varying-content', action='store_true', help='vary body size and position between content-fit slices')
parser.add_argument('--content-count', type=int, default=8, help='number of content-fit slices')
arguments = parser.parse_args()
if arguments.curved_table and not arguments.content_fit:
    parser.error('--curved-table requires --content-fit')
if arguments.varying_content and not arguments.content_fit:
    parser.error('--varying-content requires --content-fit')
if arguments.content_count < 1:
    parser.error('--content-count must be positive')

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

    dataset.file_meta.MediaStorageSOPClassUID = dataset.SOPClassUID

    dataset.PixelData = pixels.astype(
        numpy.int16 if dataset.PixelRepresentation else numpy.uint16).tobytes()

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-22s %-48s %s' % (name, description, path.name))


if arguments.content_fit:
    yy, xx = numpy.mgrid[:size, :size]
    x, y = xx / size, yy / size
    series, frame_of_reference = generate_uid(), generate_uid()
    for index in range(arguments.content_count):
        cx, cy = (.5, .41) if arguments.curved_table else (.59, .60)
        body = ((x - cx) / .27) ** 2 + ((y - cy) / (.18 + index * .002)) ** 2 <= 1
        arm = ((x - .17) / .06) ** 2 + ((y - cy) / .10) ** 2 <= 1
        if arguments.varying_content:
            phase = numpy.sin(numpy.pi * index / max(1, arguments.content_count - 1)) ** 2
            cx, cy = .45 + .10 * phase, .30 + .18 * phase
            body = ((x - cx) / (.12 + .19 * phase)) ** 2 + ((y - cy) / (.10 + .20 * phase)) ** 2 <= 1
            arm = ((x - .14) / .06) ** 2 + ((y - cy) / .10) ** 2 <= 1
        pixels = ((xx * 7 + yy * 3) % 5).astype(numpy.uint16)
        pixels[body | arm] = 1800 + ((xx[body | arm] + yy[body | arm]) % 500)
        if arguments.curved_table:
            curve = .89 - .6 * (x - .5) ** 2
            rails = (numpy.abs(y - curve) < .007) | (numpy.abs(y - curve - .035) < .007)
            ends = (numpy.abs(x - .05) < .007) | (numpy.abs(x - .95) < .007)
            table = ((x >= .043) & (x <= .957)
                     & (rails | (ends & (y >= curve) & (y <= curve + .035))))
            pixels[table] = 3000
        else:
            pixels[int(size * .92), int(size * .05):int(size * .95)] = 3000
        pixels[int(size * .10), int(size * .95)] = 4095
        description = 'offset body, separate arm and curved table' if arguments.curved_table else 'offset content with separate arm and thin table'
        if arguments.varying_content:
            description = 'varying body extent across slices'
        build('content-fit-%02d' % index, 1, description, pixels,
              PatientName='SYNTHETIC^CONTENTFIT', PatientID='CONTENT-FIT',
              SOPClassUID=CTImageStorage, Modality='CT',
              StudyDescription='Synthetic opening content auto-zoom', StudyID='CFIT',
              SeriesInstanceUID=series, FrameOfReferenceUID=frame_of_reference,
              InstanceNumber=index + 1, ImageOrientationPatient=[1, 0, 0, 0, 1, 0],
              ImagePositionPatient=[0, 0, index], SliceThickness=1, PixelSpacing=[1, 1],
              WindowCenter=1500, WindowWidth=3000)
    raise SystemExit(0)

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
