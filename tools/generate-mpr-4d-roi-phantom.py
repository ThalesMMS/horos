#!/usr/bin/env python3
"""4D CT phantom with a distinct HU per time, same geometry, for MPR ROI stats.

Import the three series, open 4D Viewer, then 3D MPR. Draw a closed ROI on an
oblique plane. Mean/min/max must equal that time's HU (50, 150, 250) and must
not keep the previous time after the slider moves. Do not commit the DICOM.

    python3 tools/generate-mpr-4d-roi-phantom.py <empty dir>
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
parser.add_argument('--slices', type=int, default=8)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

TIMES = (50, 150, 250)
AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
study = generate_uid()
study_id = '226'
size = arguments.size
slices = arguments.slices
if size < 8 or slices < 4:
    raise SystemExit('need at least 8×8×4 so an oblique ROI still sits in-volume')

for time, hu in enumerate(TIMES):
    series = generate_uid()
    picture = numpy.full((size, size), hu, dtype=numpy.uint16)
    for z in range(slices):
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
        dataset.PatientName = 'LOCAL^MPR-4D-ROI'
        dataset.PatientID = 'MPR-4D-226'
        dataset.PatientBirthDate = '19700101'
        dataset.PatientSex = 'O'
        dataset.StudyDate = '20260911'
        dataset.StudyTime = '120000'
        dataset.ContentDate = '20260911'
        dataset.ContentTime = '120000'
        dataset.AccessionNumber = 'MPR226'
        dataset.StudyID = study_id
        dataset.SeriesNumber = time + 1
        dataset.InstanceNumber = z + 1
        dataset.Modality = 'CT'
        dataset.StudyDescription = 'synthetic 4D MPR ROI statistics phantom'
        dataset.SeriesDescription = 'ROI time %d HU %d' % (time, hu)
        dataset.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
        dataset.ImagePositionPatient = [0.0, 0.0, float(z)]
        dataset.ImageOrientationPatient = AXIAL
        dataset.SliceLocation = float(z)
        dataset.PixelSpacing = [1.0, 1.0]
        dataset.SliceThickness = 1.0
        dataset.SpacingBetweenSlices = 1.0
        dataset.RescaleIntercept = 0.0
        dataset.RescaleSlope = 1.0
        dataset.RescaleType = 'HU'
        dataset.NumberOfTemporalPositions = len(TIMES)
        dataset.TemporalPositionIdentifier = time + 1
        dataset.Rows = size
        dataset.Columns = size
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = 'MONOCHROME2'
        dataset.BitsAllocated = 16
        dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 0
        dataset.PixelData = picture.tobytes()
        name = 't%02d-z%02d.dcm' % (time, z)
        dataset.save_as(str(arguments.destination / name), write_like_original=False)

print('times             %d (HU %s)' % (len(TIMES), ', '.join(str(v) for v in TIMES)))
print('geometry          %d slices, %d×%d, 1 mm isotropic, same IPP/IOP' % (slices, size, size))
print('oblique ROI       mean = min = max = HU of the selected time')
print('cache             previous time must not remain after the slider moves')
print('wrote             %s' % arguments.destination)
