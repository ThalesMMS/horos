#!/usr/bin/env python3
"""PALETTE COLOR nuclear medicine images with lookup tables that are known.

Every variant carries the same index picture - a left-to-right ramp over the
whole range the palette maps - and the same colour scheme, chosen so that the
three channels cannot be mistaken for one another:

    red    rises with the index
    green  falls with the index
    blue   is constant

A reader that takes the blue table from the green attribute produces a falling
blue; one that ignores the descriptor's first mapped value produces a ramp that
starts in the wrong place; one that divides a 16-bit entry by 256 when the entry
only uses eight bits produces black.

    8bit           BitsAllocated 8, descriptor [256, 0, 8], 8-bit table entries
    16bit-narrow   descriptor [256, 0, 16] with entries that hold 0-255, which is
                   what a lot of nuclear medicine equipment writes
    16bit-wide     descriptor [256, 0, 16] with entries that use all 16 bits
    16bit-pixels   BitsAllocated 16, 4096 entries, a 12-bit index ramp
    offset         BitsAllocated 16, descriptor [256, 1000, 8]: the first entry
                   stands for pixel value 1000
    us-cine        the same 16-bit palette over 8 ultrasound frames, which is the
                   shape a converted cine loop has, not 0
"""
import argparse
import json
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

NUCLEAR_MEDICINE = '1.2.840.10008.5.1.4.1.1.20'
ULTRASOUND_MULTIFRAME = '1.2.840.10008.5.1.4.1.1.3.1'

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


def scheme(entries):
    """The colour of each entry, as 8-bit values."""
    index = numpy.arange(entries)
    red = (index * 255 // max(entries - 1, 1)).astype(numpy.uint16)
    green = 255 - red
    blue = numpy.full(entries, BLUE, dtype=numpy.uint16)
    return red, green, blue


def indices(entries, first):
    """A left-to-right ramp over the values the palette maps."""
    line = numpy.linspace(first, first + entries - 1, columns)
    return numpy.tile(line, (rows, 1))


def build(name, series_number, description, entries, first, allocated, table_bits, wide,
          frames=1):
    instance = generate_uid()
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    sop_class = ULTRASOUND_MULTIFRAME if frames > 1 else NUCLEAR_MEDICINE
    dataset.file_meta.MediaStorageSOPClassUID = sop_class
    dataset.file_meta.MediaStorageSOPInstanceUID = instance
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.file_meta.ImplementationClassUID = generate_uid()

    dataset.SpecificCharacterSet = 'ISO_IR 100'
    dataset.SOPClassUID = sop_class
    dataset.SOPInstanceUID = instance
    dataset.StudyInstanceUID = study
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = 'PALETTE^NM'
    dataset.PatientID = 'PAL-97'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'PAL97'
    dataset.StudyID = '97'
    dataset.SeriesNumber = series_number
    dataset.InstanceNumber = 1
    dataset.Modality = 'US' if frames > 1 else 'NM'
    dataset.StudyDescription = 'PALETTE COLOR lookup tables'
    dataset.SeriesDescription = description
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'STATIC']
    if frames > 1:
        dataset.NumberOfFrames = frames
        dataset.FrameIncrementPointer = 0x00181063
        dataset.FrameTime = 33.0

    dataset.Rows = rows
    dataset.Columns = columns
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'PALETTE COLOR'
    dataset.BitsAllocated = allocated
    dataset.BitsStored = allocated
    dataset.HighBit = allocated - 1
    dataset.PixelRepresentation = 0

    red, green, blue = scheme(entries)
    descriptor = [entries if entries < 65536 else 0, first, table_bits]
    dataset.RedPaletteColorLookupTableDescriptor = list(descriptor)
    dataset.GreenPaletteColorLookupTableDescriptor = list(descriptor)
    dataset.BluePaletteColorLookupTableDescriptor = list(descriptor)

    if table_bits == 8:
        pack = lambda values: values.astype(numpy.uint8).tobytes()
    elif wide:
        # Entries that use all sixteen bits: 0-255 spread over 0-65535.
        pack = lambda values: (values * 257).astype(numpy.uint16).tobytes()
    else:
        pack = lambda values: values.astype(numpy.uint16).tobytes()

    dataset.RedPaletteColorLookupTableData = pack(red)
    dataset.GreenPaletteColorLookupTableData = pack(green)
    dataset.BluePaletteColorLookupTableData = pack(blue)

    plane = indices(entries, first)
    pixels = numpy.stack([plane] * frames) if frames > 1 else plane
    dataset.PixelData = pixels.astype(numpy.uint8 if allocated == 8
                                      else numpy.uint16).tobytes()

    path = arguments.destination / ('%s.dcm' % name)
    dataset.save_as(str(path), enforce_file_format=True)
    print('%-14s %-52s %d entries from %d, %d-bit table, %d-bit pixels, %d frame(s)'
          % (name, description, entries, first, table_bits, allocated, frames))
    return {'name': name, 'series': description, 'entries': entries, 'first': first,
            'red': [int(v) for v in red], 'green': [int(v) for v in green],
            'blue': [int(v) for v in blue],
            'columns': [float(v) for v in numpy.linspace(first, first + entries - 1, columns)]}


expected = [
    build('8bit', 1, '8-bit palette, 8-bit entries', 256, 0, 8, 8, False),
    build('16bit-narrow', 2, '16-bit palette holding 8-bit values', 256, 0, 16, 16, False),
    build('16bit-wide', 3, '16-bit palette using all sixteen bits', 256, 0, 16, 16, True),
    build('16bit-pixels', 4, '12-bit index ramp over 4096 entries', 4096, 0, 16, 16, True),
    build('offset', 5, 'first entry stands for pixel value 1000', 256, 1000, 16, 8, False),
    build('us-cine', 6, '16-bit ultrasound palette over 8 frames', 4096, 0, 16, 16, True,
          frames=8),
]

(arguments.destination / 'expected.json').write_text(json.dumps(expected, indent=1))
print()
print('study %s' % study)
print('blue is a constant %d in every variant' % BLUE)
