#!/usr/bin/env python3
"""Two parallel axial slices with known marker pixels for inter-slice measure.

Place a t2DPoint on each bright marker, then run Measure Between Slices.
With pixel-center conversion the in-plane shift is identical on both slices,
so the projection is 20 mm and the 3D length is sqrt(20² + spacing²) mm.

    python3 tools/generate-interslice-measure-fixture.py <empty dir>
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--spacing', type=float, default=5.0, help='mm between slices')
parser.add_argument('--size', type=int, default=32)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
if size < 22:
    raise SystemExit('size must be at least 22 so both markers fit')

study = generate_uid()
series = generate_uid()
AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
MARKERS = ((0, (10, 0)), (1, (10, 20)))


def picture(column, row):
    image = numpy.full((size, size), 40, dtype=numpy.uint16)
    image[row, column] = 2000
    image[:, :1] = 80
    return image


for index, (column, row) in MARKERS:
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
    dataset.PatientName = 'INTERSLICE^MEASURE'
    dataset.PatientID = 'ISL-257'
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260911'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260911'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'ISL257'
    dataset.StudyID = '257'
    dataset.SeriesNumber = 1
    dataset.InstanceNumber = index + 1
    dataset.Modality = 'CT'
    dataset.StudyDescription = 'synthetic inter-slice measure phantom'
    dataset.SeriesDescription = 'parallel axials, 20 mm in-plane, known z'
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    dataset.ImagePositionPatient = [0.0, 0.0, index * arguments.spacing]
    dataset.ImageOrientationPatient = AXIAL
    dataset.SliceLocation = float(index * arguments.spacing)
    dataset.PixelSpacing = [1.0, 1.0]
    dataset.SliceThickness = arguments.spacing
    dataset.SpacingBetweenSlices = arguments.spacing
    dataset.Rows = size
    dataset.Columns = size
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelData = picture(column, row).tobytes()
    dataset.save_as(str(arguments.destination / ('slice-%d.dcm' % (index + 1))),
                    write_like_original=False)

proj = 20.0
dist3d = (proj ** 2 + arguments.spacing ** 2) ** 0.5
print('slices            2 axial, IOP 1,0,0,0,1,0')
print('markers           (10, 0) at z=0 and (10, 20) at z=%.1f mm' % arguments.spacing)
print('projection        %.2f mm' % proj)
print('distance3D        %.4f mm' % dist3d)
print('unit              mm')
print('orientation       axial')
print('wrote             %s' % arguments.destination)
