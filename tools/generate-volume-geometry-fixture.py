#!/usr/bin/env python3
"""Slice stacks whose geometry is regular, and stacks whose geometry is not.

A volume is built from separate instances by reading each one's Image Position
Patient and Image Orientation Patient. The reports are of imported volumes that
come out misaligned, with no dataset attached, so this writes the shapes that
produce that - and a control that does not - and each slice carries a picture
that says where it belongs:

    regular        evenly spaced, one orientation: the control
    isotropic      optional 1 mm pixel and slice interval (--also-isotropic)
    gap            one slice missing from the middle of the stack
    jitter         one slice displaced sideways, off the stack's own axis
    tilted         one slice rotated, so the stack has two orientations
    uneven         the spacing changes half way down
    positions-lie  positions and instance numbers disagree about the order

Every slice is a dark field with a bright bar whose height says which slice it
is: a coronal or axial reformat of a regular stack is a staircase, and one built
from a stack that was misread is not.

    python3 tools/generate-volume-geometry-fixture.py <empty dir> [--slices 16]
    python3 tools/generate-volume-geometry-fixture.py <empty dir> --also-isotropic
"""
import argparse
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--slices', type=int, default=16)
parser.add_argument('--size', type=int, default=64)
parser.add_argument('--spacing', type=float, default=2.0, help='mm between slices')
parser.add_argument('--also-isotropic', action='store_true',
                    help='also write a 1 mm isotropic stack for Curved MPR (#31)')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
study = generate_uid()
AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]


def picture(index, count):
    """A bright bar whose height is this slice's place in the stack."""
    image = numpy.zeros((size, size), dtype=numpy.uint16)
    top = size - 1 - int((size - 4) * index / max(count - 1, 1))
    image[max(top - 2, 0):top + 2, size // 4: 3 * size // 4] = 2000
    image[:, :2] = 500                       # a rail, so an empty slice is visible
    return image


def build(series, number, description, slices, pixel=0.5, slice_spacing=None):
    interval = arguments.spacing if slice_spacing is None else slice_spacing
    series_uid = generate_uid()
    for position, (index, origin, orientation, instance) in enumerate(slices):
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
        dataset.SeriesInstanceUID = series_uid
        dataset.PatientName = 'VOLUME^GEOMETRY'
        dataset.PatientID = 'VOL-102'
        dataset.PatientBirthDate = '19700101'
        dataset.PatientSex = 'O'
        dataset.StudyDate = '20260101'
        dataset.StudyTime = '120000'
        dataset.ContentDate = '20260101'
        dataset.ContentTime = '120000'
        dataset.AccessionNumber = 'VOL102'
        dataset.StudyID = '102'
        dataset.SeriesNumber = number
        dataset.InstanceNumber = instance
        dataset.Modality = 'CT'
        dataset.StudyDescription = 'stacks that are a volume, and stacks that are not'
        dataset.SeriesDescription = description
        dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
        dataset.ImagePositionPatient = [float(v) for v in origin]
        dataset.ImageOrientationPatient = [float(v) for v in orientation]
        dataset.SliceLocation = float(origin[2])
        dataset.PixelSpacing = [pixel, pixel]
        dataset.SliceThickness = interval
        dataset.SpacingBetweenSlices = interval

        dataset.Rows = size
        dataset.Columns = size
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = 'MONOCHROME2'
        dataset.BitsAllocated = 16
        dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 0
        dataset.WindowCenter = 1000.0
        dataset.WindowWidth = 2000.0
        dataset.RescaleIntercept = 0.0
        dataset.RescaleSlope = 1.0
        dataset.PixelData = picture(index, arguments.slices).tobytes()

        dataset.save_as(str(arguments.destination / ('%s-%02d.dcm' % (series, position))),
                        enforce_file_format=True)
    print('%-14s %-52s %2d slices' % (series, description, len(slices)))
    return series_uid


count = arguments.slices
step = arguments.spacing


def stack(step=None, **changes):
    out = []
    rise = arguments.spacing if step is None else step
    for index in range(count):
        origin = [0.0, 0.0, index * rise]
        orientation = list(AXIAL)
        instance = index + 1
        if changes.get('drop') == index:
            continue
        if changes.get('jitter') == index:
            origin[0] += 8.0
        if changes.get('tilt') == index:
            orientation = [1.0, 0.0, 0.0, 0.0, 0.9659, 0.2588]     # 15 degrees
        if changes.get('uneven') and index >= count // 2:
            origin[2] = (count // 2) * rise + (index - count // 2) * rise * 3
        if changes.get('lie'):
            instance = count - index
        out.append((index, origin, orientation, instance))
    return out


print('study %s' % study)
build('regular', 1, 'evenly spaced, one orientation', stack())
build('gap', 2, 'one slice missing from the middle', stack(drop=count // 2))
build('jitter', 3, 'one slice displaced 8 mm sideways', stack(jitter=count // 2))
build('tilted', 4, 'one slice rotated 15 degrees', stack(tilt=count // 2))
build('uneven', 5, 'the spacing triples half way down', stack(uneven=True))
build('positions-lie', 6, 'instance numbers count the other way', stack(lie=True))
if arguments.also_isotropic:
    build('isotropic', 7, '1 mm pixel and 1 mm slice interval',
          stack(step=1.0), pixel=1.0, slice_spacing=1.0)
print('patient VOLUME^GEOMETRY / VOL-102')
