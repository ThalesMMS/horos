#!/usr/bin/env python3
"""Create a synthetic 150-series CT study; requires pydicom, contains no patient data."""
import argparse
from pathlib import Path
import struct
import uuid
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

def uid(name):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:series-navigation:' + name).int)

def generate(output, count):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use an empty output directory to avoid mixing or overwriting fixtures")
    for number in range(1, count + 1):
        instance = uid(f'instance-{number}')
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = instance
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(str(output / f'{number:03d}.dcm'), {}, file_meta=meta, preamble=b'\0' * 128)
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = instance
        ds.PatientName = 'QA^Series Navigation'
        ds.PatientID = 'LOCAL-SERIES-NAVIGATION'
        ds.StudyInstanceUID = uid('study')
        ds.SeriesInstanceUID = uid(f'series-{number}')
        ds.FrameOfReferenceUID = uid('frame')
        ds.StudyDate = ds.SeriesDate = ds.AcquisitionDate = ds.ContentDate = '20260907'
        ds.StudyTime = ds.SeriesTime = ds.AcquisitionTime = ds.ContentTime = '120000'
        ds.StudyID = 'NAV150'
        ds.AccessionNumber = 'SYNTHETIC-NAV150'
        ds.StudyDescription = 'Synthetic 150 Series Navigation'
        ds.SeriesDescription = f'Navigation series {number:03d}'
        ds.SeriesNumber = number
        ds.InstanceNumber = 1
        ds.Modality = 'CT'
        ds.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
        ds.Rows = ds.Columns = 32
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        ds.PixelSpacing = [1, 1]
        ds.SliceThickness = 1
        ds.ImagePositionPatient = [0, 0, 0]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.RescaleIntercept = 0
        ds.RescaleSlope = 1
        ds.WindowCenter = 512
        ds.WindowWidth = 1024
        ds.PixelData = struct.pack('<1024H', *(x + number for x in range(1024)))
        ds.save_as(ds.filename, enforce_file_format=True)
    print(f'Created {count} synthetic series in {output}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--count', type=int, default=150)
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error('count must be between 1 and 1000')
    generate(args.output, args.count)
