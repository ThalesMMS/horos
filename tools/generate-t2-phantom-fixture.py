#!/usr/bin/env python3
"""Synthetic multi-echo MR phantom with four known T2 compartments.

Does not write into the repository. Destination must be empty.

    python3 tools/generate-t2-phantom-fixture.py <empty dir>
"""
import argparse
import math
import struct
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

TES_MS = (10.0, 20.0, 40.0, 80.0)
T2_MS = (40.0, 80.0, 120.0, 200.0)
S0 = 1000.0


def compartment(row, column, size):
    return T2_MS[(0 if row < size // 2 else 2) + (0 if column < size // 2 else 1)]


def frame(size, te):
    values = []
    for row in range(size):
        for column in range(size):
            t2 = compartment(row, column, size)
            values.append(int(round(S0 * math.exp(-te / t2))))
    return struct.pack('<%dH' % (size * size), *values)


def generate(destination, size=32):
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise SystemExit('%s is not empty' % destination)
    study = generate_uid()
    series = generate_uid()
    for index, te in enumerate(TES_MS):
        sop = generate_uid()
        dataset = Dataset()
        dataset.file_meta = FileMetaDataset()
        dataset.file_meta.MediaStorageSOPClassUID = MRImageStorage
        dataset.file_meta.MediaStorageSOPInstanceUID = sop
        dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        dataset.file_meta.ImplementationClassUID = generate_uid()
        dataset.SpecificCharacterSet = 'ISO_IR 100'
        dataset.SOPClassUID = MRImageStorage
        dataset.SOPInstanceUID = sop
        dataset.StudyInstanceUID = study
        dataset.SeriesInstanceUID = series
        dataset.PatientName = 'T2^PHANTOM'
        dataset.PatientID = 'T2-156'
        dataset.PatientBirthDate = '19700101'
        dataset.PatientSex = 'O'
        dataset.StudyDate = '20260911'
        dataset.StudyTime = '120000'
        dataset.ContentDate = '20260911'
        dataset.ContentTime = '120000'
        dataset.AccessionNumber = 'T2156'
        dataset.StudyID = '156'
        dataset.StudyDescription = 'T2 Fit Map Phantom'
        dataset.SeriesDescription = 'SE multi-echo T2 phantom'
        dataset.SeriesNumber = 1
        dataset.InstanceNumber = index + 1
        dataset.Modality = 'MR'
        dataset.Manufacturer = 'Synthetic fixture'
        dataset.Rows = dataset.Columns = size
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = 'MONOCHROME2'
        dataset.BitsAllocated = dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 0
        dataset.PixelSpacing = [1.0, 1.0]
        dataset.SliceThickness = 5.0
        dataset.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        dataset.ImagePositionPatient = [0.0, 0.0, 0.0]
        dataset.FrameOfReferenceUID = generate_uid()
        dataset.EchoTime = te
        dataset.EchoNumbers = index + 1
        dataset.RepetitionTime = 2000.0
        dataset.ScanningSequence = 'SE'
        dataset.SequenceVariant = 'NONE'
        dataset.ScanOptions = ''
        dataset.MRAcquisitionType = '2D'
        dataset.PixelData = frame(size, te)
        dataset.save_as(destination / ('echo-%d.dcm' % (index + 1)), enforce_file_format=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--size', type=int, default=32)
    arguments = parser.parse_args()
    generate(arguments.destination, arguments.size)
    print('Wrote four echo images to', arguments.destination)
