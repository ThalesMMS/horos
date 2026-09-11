#!/usr/bin/env python3
"""Images whose declared shape does not describe their pixels.

The reports are of a crash while building a thumbnail, and of studies shown as
bands of lines rather than the examination. Both come from an object whose
dimensions and pixel data disagree, so this makes objects that disagree in every
way one can:

    zero-rows        Rows 0, Columns 64
    zero-columns     Rows 64, Columns 0
    zero-both        Rows 0, Columns 0
    no-pixels        64x64 declared, no Pixel Data element at all
    empty-pixels     64x64 declared, a Pixel Data element of zero length
    half-a-multiframe  four frames declared, two frames of pixels
    short-pixels     64x64 declared, four bytes of pixel data
    zero-spacing     64x64 with PixelSpacing 0\\0 and SliceThickness 0
    huge-declared    16384x16384 declared, one row of pixels
    empty-fragment   64x64 JPEG baseline whose one fragment is empty
    broken-fragment  64x64 JPEG baseline whose fragment is not a JPEG

Each is its own series, so a thumbnail that is not built leaves a series that can
still be told apart from one that was.
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
import struct

from pydicom.uid import (CTImageStorage, ExplicitVRLittleEndian, JPEGBaseline8Bit,
                         generate_uid)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

study = generate_uid()


def encapsulated(fragment):
    """One fragment, written by hand.

    pydicom's encapsulate() refuses a fragment shorter than two bytes, and an
    empty fragment is exactly the case being built: a frame the codec is asked
    to decode and there is nothing to decode.
    """
    item = b'\xfe\xff\x00\xe0'
    padded = fragment + (b'\x00' if len(fragment) % 2 else b'')
    return (item + struct.pack('<I', 0)                       # empty offset table
            + item + struct.pack('<I', len(padded)) + padded)


def build(name, series_number, description, rows, columns, pixels,
          spacing=(0.5, 0.5), thickness=1.0, frames=1, fragment=None):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = (JPEGBaseline8Bit if fragment is not None
                                           else ExplicitVRLittleEndian)
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'DEGENERATE^SHAPE'
    dataset.PatientID = 'DEGEN-123'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'DEGEN123'
    dataset.StudyID = '123'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'CT'
    dataset.StudyDescription = 'shapes that do not describe their pixels'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    dataset.ImagePositionPatient = [0.0, 0.0, float(series_number)]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.PixelSpacing = list(spacing)
    dataset.SliceThickness = thickness

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
    if frames > 1:
        dataset.NumberOfFrames = frames
    if fragment is not None:
        # Encapsulated, so the frame is a fragment the codec is asked to decode
        # rather than pixels: this is the shape a truncated transfer leaves.
        dataset.BitsAllocated = 8
        dataset.BitsStored = 8
        dataset.HighBit = 7
        dataset.WindowCenter = 128.0
        dataset.WindowWidth = 256.0
        dataset.PixelData = encapsulated(fragment)
        dataset['PixelData'].is_undefined_length = True
    elif pixels is not None:
        dataset.PixelData = pixels.tobytes()

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-16s %-52s %dx%d, %s bytes of pixel data'
          % (name, description, rows, columns,
             len(dataset.PixelData) if 'PixelData' in dataset else 'no'))


ramp = numpy.tile(numpy.linspace(0, 4000, 64), (64, 1)).astype(numpy.uint16)

build('zero-rows', 1, 'Rows 0', 0, 64, numpy.zeros(0, dtype=numpy.uint16))
build('zero-columns', 2, 'Columns 0', 64, 0, numpy.zeros(0, dtype=numpy.uint16))
build('zero-both', 3, 'Rows and Columns both 0', 0, 0, numpy.zeros(0, dtype=numpy.uint16))
build('no-pixels', 4, '64x64 with no Pixel Data at all', 64, 64, None)
build('short-pixels', 5, '64x64 with four bytes of pixels', 64, 64,
      numpy.zeros(2, dtype=numpy.uint16))
build('zero-spacing', 6, '64x64 with PixelSpacing 0', 64, 64, ramp,
      spacing=(0.0, 0.0), thickness=0.0)
build('huge-declared', 7, '16384x16384 with one row of pixels', 16384, 16384,
      numpy.zeros(16384, dtype=numpy.uint16))
build('empty-pixels', 8, '64x64 with a Pixel Data element of zero length', 64, 64,
      numpy.zeros(0, dtype=numpy.uint16))
build('half-a-multiframe', 9, 'four frames declared, two frames of pixels', 64, 64,
      numpy.stack([ramp, ramp]), frames=4)
# The first frame of these two decodes to nothing, which is the branch that used
# to invent a ramp of 0..width-1 on every row - bands where the examination
# should be. The transfer syntax is named, which the original report's was not.
build('empty-fragment', 10, '64x64 JPEG baseline with an empty fragment', 64, 64, None,
      fragment=b'')
build('broken-fragment', 11, '64x64 JPEG baseline with a fragment that is not a JPEG', 64, 64,
      None, fragment=b'this is not a JPEG stream, and the codec will say so' * 8)

print()
print('study %s' % study)
