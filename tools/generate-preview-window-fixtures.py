#!/usr/bin/env python3
"""Phantom series for the database preview's window policy (#608).

One study, one series per case the acceptance names, each with a window that is
known before the application is started:

    ct-window        CT with a valid Window Center/Width; it must be kept
    ct-no-window     the same pixels with no window at all; computed instead
    mr-window        MR with a stored window; the computed one wins for MR
    mr-zero          MR over a dominant zero background; the zeros are excluded
    pt-counts        PT counts over an empty background; the low end is zero
    nm-counts        NM, the same rule
    us-colour        an RGB frame; it must never receive a scalar window
    mono1            MONOCHROME1 with a valid window; polarity is presentation
    invalid-window   Window Width 0; automatic selection, not a width of one
    multiframe       eight frames in one file, one series, one geometry

Every value here is written by this file. No patient data is involved, and the
files are for a disposable database - they are not to be committed.

    python3 tools/generate-preview-window-fixtures.py <empty dir>
"""
import argparse
import json
from pathlib import Path

import numpy
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (CTImageStorage, MRImageStorage, PositronEmissionTomographyImageStorage,
                         NuclearMedicineImageStorage, UltrasoundImageStorage,
                         ExplicitVRLittleEndian, generate_uid)

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--patient-id', default='PREVIEW-WINDOW-608')
arguments = parser.parse_args()

destination = arguments.destination
destination.mkdir(parents=True, exist_ok=True)
if any(destination.iterdir()):
    raise SystemExit('%s is not empty' % destination)

ROWS = COLUMNS = 64                      # 4096 pixels: under the sample budget
STUDY_UID = generate_uid()
FRAME_OF_REFERENCE = generate_uid()


def base(sop_class, modality, series_number, description, rows=ROWS, columns=COLUMNS):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = generate_uid()

    ds = Dataset()
    ds.file_meta = meta
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.SOPClassUID = sop_class
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.PatientName = 'Preview^Window'
    ds.PatientID = arguments.patient_id
    ds.PatientBirthDate = '19700101'
    ds.PatientSex = 'O'
    ds.StudyInstanceUID = STUDY_UID
    ds.StudyDate = '20260914'
    ds.StudyTime = '090000'
    ds.StudyID = '608'
    ds.AccessionNumber = 'PREVIEW608'
    ds.StudyDescription = 'Preview window phantoms (#608)'
    ds.SeriesInstanceUID = generate_uid()
    ds.SeriesNumber = series_number
    ds.SeriesDescription = description
    ds.Modality = modality
    ds.InstanceNumber = 1
    ds.FrameOfReferenceUID = FRAME_OF_REFERENCE
    ds.Rows = rows
    ds.Columns = columns
    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = 1.0
    ds.ImagePositionPatient = [0.0, 0.0, 0.0]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    return ds


def scalar(ds, values, bits_stored=16, signed=False, slope=1.0, intercept=0.0,
           photometric='MONOCHROME2'):
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = photometric
    ds.BitsAllocated = 16
    ds.BitsStored = bits_stored
    ds.HighBit = bits_stored - 1
    ds.PixelRepresentation = 1 if signed else 0
    ds.RescaleSlope = slope
    ds.RescaleIntercept = intercept
    stored = numpy.rint((values - intercept) / slope).astype(
        numpy.int16 if signed else numpy.uint16)
    ds.PixelData = stored.tobytes()
    return ds


def disc(value_inside, value_outside, radius=20.0, rows=ROWS, columns=COLUMNS):
    """A filled disc of one value on a background of another."""
    y, x = numpy.mgrid[0:rows, 0:columns]
    centre = ((rows - 1) / 2.0, (columns - 1) / 2.0)
    inside = ((y - centre[0]) ** 2 + (x - centre[1]) ** 2) <= radius ** 2
    return numpy.where(inside, value_inside, value_outside).astype(numpy.float64)


def ramp_disc(low, high, background, radius=20.0, rows=ROWS, columns=COLUMNS):
    """A disc whose values ramp from low to high, on a flat background."""
    y, x = numpy.mgrid[0:rows, 0:columns]
    centre = ((rows - 1) / 2.0, (columns - 1) / 2.0)
    distance = numpy.sqrt((y - centre[0]) ** 2 + (x - centre[1]) ** 2)
    inside = distance <= radius
    ramp = low + (high - low) * numpy.clip(distance / radius, 0, 1)
    return numpy.where(inside, ramp, background).astype(numpy.float64)


manifest = []


def write(ds, name, expectation):
    path = destination / (name + '.dcm')
    ds.save_as(path, enforce_file_format=True)
    manifest.append(dict(expectation, file=path.name, series=ds.SeriesDescription,
                         seriesInstanceUID=ds.SeriesInstanceUID, modality=ds.Modality))


# 1. CT with a valid window: it is kept, whatever the pixels say.
ct = scalar(base(CTImageStorage, 'CT', 1, 'ct-window'),
            ramp_disc(-200.0, 900.0, -1000.0), intercept=-1024.0)
ct.WindowCenter = 40.0
ct.WindowWidth = 400.0
write(ct, 'ct-window', {'expect': 'dicom', 'level': 40.0, 'width': 400.0})

# 2. The same pixels with no window: computed from the intensities.
write(scalar(base(CTImageStorage, 'CT', 2, 'ct-no-window'),
             ramp_disc(-200.0, 900.0, -1000.0), intercept=-1024.0),
      'ct-no-window', {'expect': 'automatic', 'rejectsBackground': -1000.0})

# 3. MR with a stored window: the computed one wins, as in the origin.
mr = scalar(base(MRImageStorage, 'MR', 3, 'mr-window'), ramp_disc(80.0, 900.0, 0.0))
mr.WindowCenter = 2000.0                 # deliberately unlike the pixels
mr.WindowWidth = 4000.0
write(mr, 'mr-window', {'expect': 'automatic', 'notLevel': 2000.0, 'notWidth': 4000.0})

# 4. MR over a dominant zero background, corners deliberately not equal.
values = ramp_disc(80.0, 900.0, 0.0)
for (row, column), corner in zip([(0, 0), (0, COLUMNS - 1), (ROWS - 1, 0), (ROWS - 1, COLUMNS - 1)],
                                 [11.0, 22.0, 33.0, 44.0]):
    values[row][column] = corner
write(scalar(base(MRImageStorage, 'MR', 4, 'mr-zero'), values),
      'mr-zero', {'expect': 'automatic', 'lowAbove': 0.0})

# 5/6. Counts over an empty background: the low end belongs at zero.
write(scalar(base(PositronEmissionTomographyImageStorage, 'PT', 5, 'pt-counts'),
             ramp_disc(3.0, 2000.0, 0.0), slope=0.5),
      'pt-counts', {'expect': 'automatic', 'low': 0.0})
write(scalar(base(NuclearMedicineImageStorage, 'NM', 6, 'nm-counts'),
             ramp_disc(3.0, 2000.0, 0.0)),
      'nm-counts', {'expect': 'automatic', 'low': 0.0})

# 7. Colour: three samples per pixel, no scalar intensity to window.
us = base(UltrasoundImageStorage, 'US', 7, 'us-colour')
us.SamplesPerPixel = 3
us.PhotometricInterpretation = 'RGB'
us.PlanarConfiguration = 0
us.BitsAllocated = 8
us.BitsStored = 8
us.HighBit = 7
us.PixelRepresentation = 0
colour = numpy.zeros((ROWS, COLUMNS, 3), dtype=numpy.uint8)
colour[..., 0] = numpy.tile(numpy.arange(COLUMNS, dtype=numpy.uint8) * 4, (ROWS, 1))
colour[..., 1] = disc(220, 20).astype(numpy.uint8)
colour[..., 2] = 128
us.PixelData = colour.tobytes()
write(us, 'us-colour', {'expect': 'color', 'level': 127.5, 'width': 255.0})

# 8. MONOCHROME1: polarity is presentation; the stored window is still valid.
mono = scalar(base(CTImageStorage, 'CT', 8, 'mono1'),
              ramp_disc(-200.0, 900.0, -1000.0), intercept=-1024.0,
              photometric='MONOCHROME1')
mono.WindowCenter = 40.0
mono.WindowWidth = 400.0
write(mono, 'mono1', {'expect': 'dicom', 'width': 400.0, 'levelMagnitude': 40.0})

# 9. Window Width 0: a request for automatic selection, not a width of one.
invalid = scalar(base(CTImageStorage, 'CT', 9, 'invalid-window'),
                 ramp_disc(-200.0, 900.0, -1000.0), intercept=-1024.0)
invalid.WindowCenter = 40.0
invalid.WindowWidth = 0.0
write(invalid, 'invalid-window', {'expect': 'automatic', 'widthAbove': 2.0})

# 10. Eight frames in one file: one series, one geometry, one window.
multi = base(MRImageStorage, 'MR', 10, 'multiframe')
frames = numpy.stack([ramp_disc(80.0 + 40 * index, 900.0, 0.0) for index in range(8)])
multi.NumberOfFrames = 8
scalar(multi, frames.reshape(-1))
multi.Rows = ROWS
multi.Columns = COLUMNS
write(multi, 'multiframe', {'expect': 'automatic', 'frames': 8})

(destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('wrote %d series to %s' % (len(manifest), destination))
for entry in manifest:
    print('  %-14s %-3s %s' % (entry['series'], entry['modality'], entry['expect']))
