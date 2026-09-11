#!/usr/bin/env python3
"""A synthetic CT volume with bone, soft tissue, vessel and air, for 3D work.

The 3D preset panel is judged by whether a preset shows what it promises: a bone
preset has to show bone and not soft tissue, a vascular one has to show the
vessel. That needs a volume whose values are real Hounsfield units and whose
structures sit at different ones, which the geometry fixtures are not - they
carry a bar chart, not a body.

So this writes a cylinder phantom, axial, in HU:

    air           -1000   outside the phantom
    fat            -100   a subcutaneous ring
    soft tissue      40   the bulk
    vessel          300   a contrast-filled tube along the axis, off-centre
    bone           1000   a posterior block and a ring of eight ribs

Nothing here comes from a person: every value is written by this file.

    python3 tools/generate-ct-phantom-fixture.py <empty dir> [--slices 200] [--size 256]
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--slices', type=int, default=200)
parser.add_argument('--size', type=int, default=256)
parser.add_argument('--spacing', type=float, default=1.0, help='mm between slices')
parser.add_argument('--patient-id', default='CT-PHANTOM-34')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
count = arguments.slices
INTERCEPT = -1024.0                      # so unsigned pixels can carry -1000 HU
AIR, FAT, SOFT, VESSEL, BONE = -1000.0, -100.0, 40.0, 300.0, 1000.0

grid = numpy.linspace(-1.0, 1.0, size)
x, y = numpy.meshgrid(grid, grid)
radius = numpy.sqrt(x * x + y * y)


def slice_hu(index):
    """One axial slice, in Hounsfield units."""
    hu = numpy.full((size, size), AIR, dtype=numpy.float32)
    body = radius < 0.80
    hu[body] = SOFT
    hu[(radius < 0.80) & (radius > 0.72)] = FAT
    # A posterior block of bone, the whole length of the volume.
    spine = (numpy.abs(x) < 0.10) & (y > 0.42) & (y < 0.60)
    hu[spine] = BONE
    # Eight ribs on a ring, present on part of the stack so a coronal view shows
    # them as separate arcs rather than tubes.
    if 0.15 * count < index < 0.85 * count:
        for k in range(8):
            angle = 2.0 * numpy.pi * k / 8.0
            cx, cy = 0.62 * numpy.cos(angle), 0.62 * numpy.sin(angle)
            rib = ((x - cx) ** 2 + (y - cy) ** 2) < 0.0036
            hu[rib] = BONE
    # A contrast-filled vessel along the axis, off-centre, drifting as it goes.
    drift = 0.18 * numpy.sin(2.0 * numpy.pi * index / max(count - 1, 1))
    vessel = ((x - drift) ** 2 + (y + 0.15) ** 2) < 0.0049
    hu[vessel] = VESSEL
    return hu


series_uid = generate_uid()
study_uid = generate_uid()
for index in range(count):
    stored = numpy.clip(slice_hu(index) - INTERCEPT, 0, 4095).astype(numpy.uint16)
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
    dataset.StudyInstanceUID = study_uid
    dataset.SeriesInstanceUID = series_uid
    dataset.PatientName = 'CT^PHANTOM'
    dataset.PatientID = arguments.patient_id
    dataset.PatientBirthDate = '19700101'
    dataset.PatientSex = 'O'
    dataset.StudyDate = '20260101'
    dataset.StudyTime = '120000'
    dataset.ContentDate = '20260101'
    dataset.ContentTime = '120000'
    dataset.AccessionNumber = 'CTP34'
    dataset.StudyID = '34'
    dataset.SeriesNumber = 1
    dataset.InstanceNumber = index + 1
    dataset.Modality = 'CT'
    dataset.StudyDescription = 'synthetic CT phantom for 3D presets'
    dataset.SeriesDescription = 'bone, vessel and soft tissue in Hounsfield units'
    dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    dataset.ImagePositionPatient = [-0.5 * size, -0.5 * size, index * arguments.spacing]
    dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    dataset.SliceLocation = float(index * arguments.spacing)
    dataset.PixelSpacing = [1.0, 1.0]
    dataset.SliceThickness = arguments.spacing
    dataset.SpacingBetweenSlices = arguments.spacing

    dataset.Rows = size
    dataset.Columns = size
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = 'MONOCHROME2'
    dataset.BitsAllocated = 16
    dataset.BitsStored = 12
    dataset.HighBit = 11
    dataset.PixelRepresentation = 0
    dataset.WindowCenter = 300.0
    dataset.WindowWidth = 1500.0
    dataset.RescaleIntercept = INTERCEPT
    dataset.RescaleSlope = 1.0
    dataset.PixelData = stored.tobytes()
    dataset.save_as(str(arguments.destination / ('phantom-%04d.dcm' % index)),
                    enforce_file_format=True)

print('%d slices of %d x %d, %.1f mm apart, series %s'
      % (count, size, size, arguments.spacing, series_uid))
print('patient %s, HU: air %d, fat %d, soft %d, vessel %d, bone %d'
      % (arguments.patient_id, AIR, FAT, SOFT, VESSEL, BONE))
