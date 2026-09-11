#!/usr/bin/env python3
"""Synthetic dynamic CT phantom with a known vessel time-attenuation curve.

Does not write into the repository. Destination must be empty.

    python3 tools/generate-roi-enhancement-fixture.py <empty dir>
"""
import argparse
import struct
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

TIMES_S = (0, 2, 4, 6, 8, 10, 12, 14)
VESSEL_HU = (40, 80, 150, 220, 200, 140, 90, 60)


def frame(size, hu):
    values = []
    inner = range(size // 4, size // 4 + size // 2)
    for row in range(size):
        for column in range(size):
            values.append(int(hu) if row in inner and column in inner else 0)
    return struct.pack('<%dh' % (size * size), *values)


def generate(destination, size=32):
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise SystemExit('%s is not empty' % destination)
    study = generate_uid()
    series = generate_uid()
    frame_of_reference = generate_uid()
    for index, (seconds, hu) in enumerate(zip(TIMES_S, VESSEL_HU)):
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
        dataset.PatientName = 'ROI^PHANTOM'
        dataset.PatientID = 'ROI-242'
        dataset.PatientBirthDate = '19700101'
        dataset.PatientSex = 'O'
        dataset.StudyDate = '20260911'
        dataset.StudyTime = '120000'
        dataset.ContentDate = '20260911'
        dataset.AcquisitionDate = '20260911'
        dataset.ContentTime = '12%04d' % seconds
        dataset.AcquisitionTime = '12%04d' % seconds
        dataset.AccessionNumber = 'ROI242'
        dataset.StudyID = '242'
        dataset.StudyDescription = 'ROI Enhancement Phantom'
        dataset.SeriesDescription = 'Dynamic CT vessel TAC phantom'
        dataset.SeriesNumber = 1
        dataset.InstanceNumber = index + 1
        dataset.TemporalPositionIdentifier = index + 1
        dataset.NumberOfTemporalPositions = len(TIMES_S)
        dataset.Modality = 'CT'
        dataset.Manufacturer = 'Synthetic fixture'
        dataset.Rows = dataset.Columns = size
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = 'MONOCHROME2'
        dataset.BitsAllocated = dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 1
        dataset.RescaleIntercept = 0
        dataset.RescaleSlope = 1
        dataset.PixelSpacing = [1.0, 1.0]
        dataset.SliceThickness = 5.0
        dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        dataset.ImagePositionPatient = [0.0, 0.0, 0.0]
        dataset.FrameOfReferenceUID = frame_of_reference
        dataset.PixelData = frame(size, hu)
        dataset.save_as(destination / ('phase-%d.dcm' % (index + 1)), enforce_file_format=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--size', type=int, default=32)
    arguments = parser.parse_args()
    generate(arguments.destination, arguments.size)
    print('Wrote eight dynamic phases to', arguments.destination)
