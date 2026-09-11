#!/usr/bin/env python3
"""Ultrasound and secondary capture images in every colour layout, one per series.

The reports are of grey studies coming back green and purple, and of colour
studies whose channels are swapped. Which of those a viewer produces depends on
three things it is told - the photometric interpretation, the planar
configuration, and how many bits each sample really uses - and on whether it
believes them.

Every variant carries the same picture: red rising left to right, green falling,
blue a constant 96, except the grayscale ones, which carry the same ramp in all
three channels so that any colour at all is a defect.

    gray-us        MONOCHROME2 ultrasound, 8-bit: has to stay grey
    rgb-interleaved   RGB, PlanarConfiguration 0 - R,G,B per pixel
    rgb-planar        RGB, PlanarConfiguration 1 - every R, then every G, then every B
    ybr-full          YBR_FULL, PlanarConfiguration 0
    ybr-full-planar   YBR_FULL, PlanarConfiguration 1
    rgb-16-8          Secondary Capture declaring BitsAllocated 16 and BitsStored 8
                      with RGB samples, which is what the workaround in DCMPix is for
    gray-says-rgb     a grey picture whose header says RGB and SamplesPerPixel 1:
                      metadata that contradicts itself
    ybr-422           YBR_FULL_422, the layout an ultrasound loop usually has:
                      two luminance samples share one pair of chrominance ones
    ybr-422-grey      the same, carrying a grey picture - Cb and Cr are both 128,
                      so anything but grey coming back is the conversion's doing
    jpeg-colour-ybr   JPEG baseline declaring YBR_FULL_422, which is what the
                      standard says a lossy colour JPEG declares
    jpeg-colour-rgb   the same JPEG bytes declaring RGB, which several writers
                      do: the codec has already converted, and converting again
                      is where a colour study comes back green and purple
    jpeg-grey         a grey JPEG, MONOCHROME2: any colour in it is a defect
"""
import argparse
import json
from pathlib import Path

import io
import struct

import numpy
from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (ExplicitVRLittleEndian, JPEGBaseline8Bit,
                         SecondaryCaptureImageStorage, UltrasoundImageStorage,
                         generate_uid)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
parser.add_argument('--rows', type=int, default=64)
parser.add_argument('--columns', type=int, default=64)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

study = generate_uid()
rows, columns = arguments.rows, arguments.columns
BLUE = 96


def picture():
    """Red rising, green falling, blue constant - as an (rows, columns, 3) array."""
    index = numpy.arange(columns)
    red = (index * 255 // max(columns - 1, 1)).astype(numpy.uint8)
    green = (255 - red).astype(numpy.uint8)
    blue = numpy.full(columns, BLUE, dtype=numpy.uint8)
    line = numpy.stack([red, green, blue], axis=1)
    return numpy.tile(line, (rows, 1, 1))


def grey():
    index = numpy.arange(columns)
    ramp = (index * 255 // max(columns - 1, 1)).astype(numpy.uint8)
    return numpy.tile(ramp, (rows, 1))


def to_ybr(rgb):
    """Full-range YCbCr, the way PS 3.3 C.7.6.3.1.2 defines YBR_FULL."""
    r = rgb[..., 0].astype(float)
    g = rgb[..., 1].astype(float)
    b = rgb[..., 2].astype(float)
    y = 0.2990 * r + 0.5870 * g + 0.1140 * b
    cb = -0.1687 * r - 0.3313 * g + 0.5000 * b + 128.0
    cr = 0.5000 * r - 0.4187 * g - 0.0813 * b + 128.0
    return numpy.clip(numpy.stack([y, cb, cr], axis=-1), 0, 255).astype(numpy.uint8)


def encapsulated(fragment):
    """One fragment and an empty basic offset table, written by hand."""
    item = b'\xfe\xff\x00\xe0'
    padded = fragment + (b'\x00' if len(fragment) % 2 else b'')
    return (item + struct.pack('<I', 0)
            + item + struct.pack('<I', len(padded)) + padded)


def jpeg(array, subsampling):
    """A baseline JPEG of the picture, as a codec would hand it to a writer."""
    out = io.BytesIO()
    Image.fromarray(array).save(out, format='JPEG', quality=95,
                                subsampling=subsampling, optimize=False)
    return out.getvalue()


def build(name, series_number, description, sop_class, samples, photometric,
          planar, allocated, stored, pixels, expected, compressed=None):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = sop_class
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = (JPEGBaseline8Bit if compressed is not None
                                           else ExplicitVRLittleEndian)
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'COLOUR^SPACE'
    dataset.PatientID = 'COLOUR-124'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'COL124'
    dataset.StudyID = '124'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'US' if sop_class == UltrasoundImageStorage else 'OT'
    dataset.StudyDescription = 'colour layouts'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY']
    dataset.ConversionType = 'WSD'

    dataset.Rows = rows
    dataset.Columns = columns
    dataset.SamplesPerPixel = samples
    dataset.PhotometricInterpretation = photometric
    if samples > 1:
        dataset.PlanarConfiguration = planar
    dataset.BitsAllocated = allocated
    dataset.BitsStored = stored
    dataset.HighBit = stored - 1
    dataset.PixelRepresentation = 0
    if compressed is not None:
        dataset.LossyImageCompression = '01'
        dataset.LossyImageCompressionMethod = 'ISO_10918_1'
        dataset.PixelData = encapsulated(compressed)
        dataset['PixelData'].is_undefined_length = True
    else:
        dataset.PixelData = pixels.tobytes()

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-17s %-56s %s, planar %s, %d/%d bits, %d sample(s)%s'
          % (name, description, photometric, planar, stored, allocated, samples,
             ', %d bytes of JPEG' % len(compressed) if compressed is not None else ''))
    return {'name': name, 'series': description, 'columns': expected}


def to_422(ybr):
    """Y1 Y2 Cb Cr for every pair of pixels, which is what YBR_FULL_422 stores."""
    pairs = ybr.reshape(rows, columns // 2, 2, 3)
    luminance = pairs[..., 0]                      # (rows, columns/2, 2)
    chrominance = pairs[:, :, 0, 1:]               # the first pixel's Cb, Cr
    packed = numpy.concatenate([luminance, chrominance], axis=2)
    return packed.astype(numpy.uint8)


colour = picture()
ramp = grey()
colour_expected = [[int(v) for v in colour[0, x]] for x in range(columns)]
grey_expected = [[int(ramp[0, x])] * 3 for x in range(columns)]

variants = [
    build('gray-us', 1, 'MONOCHROME2 ultrasound', UltrasoundImageStorage, 1,
          'MONOCHROME2', 0, 8, 8, ramp, grey_expected),
    build('rgb-interleaved', 2, 'RGB with the samples interleaved',
          UltrasoundImageStorage, 3, 'RGB', 0, 8, 8, colour, colour_expected),
    build('rgb-planar', 3, 'RGB stored plane by plane', UltrasoundImageStorage, 3,
          'RGB', 1, 8, 8, numpy.ascontiguousarray(colour.transpose(2, 0, 1)),
          colour_expected),
    build('ybr-full', 4, 'YBR_FULL with the samples interleaved',
          UltrasoundImageStorage, 3, 'YBR_FULL', 0, 8, 8, to_ybr(colour), colour_expected),
    build('ybr-full-planar', 5, 'YBR_FULL stored plane by plane',
          UltrasoundImageStorage, 3, 'YBR_FULL', 1, 8, 8,
          numpy.ascontiguousarray(to_ybr(colour).transpose(2, 0, 1)), colour_expected),
    build('rgb-16-8', 6, 'RGB samples in 16-bit words, 8 bits stored',
          SecondaryCaptureImageStorage, 3, 'RGB', 0, 16, 8,
          colour.astype(numpy.uint16), colour_expected),
    build('gray-says-rgb', 7, 'a grey picture whose header says RGB',
          UltrasoundImageStorage, 1, 'RGB', 0, 8, 8, ramp, grey_expected),
    build('ybr-422', 8, 'YBR_FULL_422, two luminance samples per chrominance pair',
          UltrasoundImageStorage, 3, 'YBR_FULL_422', 0, 8, 8, to_422(to_ybr(colour)),
          colour_expected),
    build('ybr-422-grey', 9, 'a grey picture stored as YBR_FULL_422',
          UltrasoundImageStorage, 3, 'YBR_FULL_422', 0, 8, 8,
          to_422(to_ybr(numpy.stack([ramp] * 3, axis=-1))), grey_expected),
    build('jpeg-colour-ybr', 10, 'a colour JPEG declaring YBR_FULL_422',
          UltrasoundImageStorage, 3, 'YBR_FULL_422', 0, 8, 8, colour, colour_expected,
          compressed=jpeg(colour, 2)),
    build('jpeg-colour-rgb', 11, 'the same colour JPEG declaring RGB',
          UltrasoundImageStorage, 3, 'RGB', 0, 8, 8, colour, colour_expected,
          compressed=jpeg(colour, 2)),
    build('jpeg-grey', 12, 'a grey JPEG, MONOCHROME2', UltrasoundImageStorage, 1,
          'MONOCHROME2', 0, 8, 8, ramp, grey_expected, compressed=jpeg(ramp, 0)),
]

(arguments.destination / 'expected.json').write_text(json.dumps(variants, indent=1))
print()
print('study %s' % study)
print('%d files; blue is a constant %d in every colour variant' % (len(variants), BLUE))
