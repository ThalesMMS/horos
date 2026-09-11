#!/usr/bin/env python3
"""Synthetic CT stacks for ROI volume: regular, uneven, gap, disconnected, SBS lie.

Each slice is a dark field. A bright 10×10 square (or two 5×5 squares) marks
the region whose area is known in mm². ImagePositionPatient is the geometry;
SpacingBetweenSlices is written so a lie can be compared against IPP.

    python3 tools/generate-roi-volume-fixture.py <empty dir>
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--size', type=int, default=32)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
if size < 20:
    raise SystemExit('size must be at least 20 so both squares fit')

study = generate_uid()
AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]


def square(left=4, top=4, width=10, height=10, extra=None):
    image = numpy.full((size, size), 40, dtype=numpy.uint16)
    image[top:top + height, left:left + width] = 2000
    if extra is not None:
        el, et, ew, eh = extra
        image[et:et + eh, el:el + ew] = 2000
    image[:, :1] = 80
    return image


def write_series(name, description, positions, spacing_between, picture_for):
    folder = arguments.destination / name
    folder.mkdir()
    series = generate_uid()
    for index, z in enumerate(positions):
        sop = generate_uid()
        dataset = Dataset()
        dataset.file_meta = FileMetaDataset()
        dataset.file_meta.MediaStorageSOPClassUID = CTImageStorage
        dataset.file_meta.MediaStorageSOPInstanceUID = sop
        dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        dataset.file_meta.ImplementationClassUID = generate_uid()
        dataset.SpecificCharacterSet = 'ISO_IR 100'
        dataset.SOPClassUID = CTImageStorage
        dataset.SOPInstanceUID = sop
        dataset.StudyInstanceUID = study
        dataset.SeriesInstanceUID = series
        dataset.PatientName = 'ROI^VOLUME'
        dataset.PatientID = 'ROI-246'
        dataset.PatientBirthDate = '19700101'
        dataset.PatientSex = 'O'
        dataset.StudyDate = '20260911'
        dataset.StudyTime = '120000'
        dataset.ContentDate = '20260911'
        dataset.ContentTime = '120000'
        dataset.AccessionNumber = 'ROI246'
        dataset.StudyID = '246'
        dataset.SeriesNumber = 1
        dataset.InstanceNumber = index + 1
        dataset.Modality = 'CT'
        dataset.StudyDescription = 'synthetic ROI volume phantom'
        dataset.SeriesDescription = description
        dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
        dataset.ImagePositionPatient = [0.0, 0.0, float(z)]
        dataset.ImageOrientationPatient = AXIAL
        dataset.SliceLocation = float(z)
        dataset.PixelSpacing = [1.0, 1.0]
        dataset.SliceThickness = 2.0
        dataset.SpacingBetweenSlices = float(spacing_between)
        dataset.Rows = size
        dataset.Columns = size
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = 'MONOCHROME2'
        dataset.BitsAllocated = 16
        dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 0
        dataset.PixelData = picture_for(index, z).tobytes()
        dataset.save_as(str(folder / ('slice-%d.dcm' % (index + 1))),
                        write_like_original=False)


write_series('regular', '2 mm IPP, 10x10 square',
             [0, 2, 4, 6, 8], 2,
             lambda index, z: square())
write_series('uneven', 'IPP 0, 2, 8 mm',
             [0, 2, 8], 2,
             lambda index, z: square())
write_series('gap', 'series 0,2,4,6; square only on first and last',
             [0, 2, 4, 6], 2,
             lambda index, z: square() if z in (0, 6) else numpy.full((size, size), 40, dtype=numpy.uint16))
write_series('disconnected', 'two 5x5 squares, 5 mm apart',
             [0, 5], 5,
             lambda index, z: square(3, 3, 5, 5, extra=(14, 14, 5, 5)))
write_series('sbs-lie', 'IPP 2 mm, SpacingBetweenSlices 99',
             [0, 2, 4, 6, 8], 99,
             lambda index, z: square())

print('regular           5 axials, IPP Δz=2 mm, 10×10 px → 1 cm², V=0.8 cm³')
print('uneven            IPP 0, 2, 8 mm, V=0.8 cm³')
print('gap               ROI on 0 and 6 mm only; occupied volume 0 without interpolate')
print('disconnected      two 5×5 px (0.5 cm²) on 0 and 5 mm, V=0.25 cm³')
print('sbs-lie           same IPP as regular, SBS=99; volume still 0.8 cm³')
print('wrote             %s' % arguments.destination)
