#!/usr/bin/env python3
"""Synthetic US ordering fixture; requires pydicom. Never uses patient source data."""
import argparse
from pathlib import Path
import uuid
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import UltrasoundImageStorage, ExplicitVRLittleEndian

def uid(name):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:acquisition-sort:' + name).int)

def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    records = [
        {'AcquisitionDateTime': '20260907120000.000002'},
        {'AcquisitionDateTime': '20260907120000.000001'},
        {'AcquisitionDateTime': '20260907120000.000003'},
        {'AcquisitionDate': '20260906', 'AcquisitionTime': '235959.9'},
        {'AcquisitionDateTime': '20260907130000+0200'},
        {},
        {'AcquisitionDateTime': '20261301120000'},  # Deliberately invalid month.
        {'AcquisitionDateTime': '20260907120000.000001'},
    ]
    for number, record in enumerate(records, 1):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = UltrasoundImageStorage
        meta.MediaStorageSOPInstanceUID = uid(str(number))
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(str(output / f'{number:02d}.dcm'), {}, file_meta=meta, preamble=b'\0' * 128)
        ds.SOPClassUID = meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.PatientName = 'QA^Acquisition Order'
        ds.PatientID = 'LOCAL-ACQUISITION-ORDER'
        ds.StudyInstanceUID = uid('study')
        ds.SeriesInstanceUID = uid('series')
        ds.StudyDate = ds.SeriesDate = ds.ContentDate = '20260907'
        ds.StudyTime = ds.SeriesTime = ds.ContentTime = '120000'
        ds.StudyID = 'ACQSORT'
        ds.StudyDescription = 'Synthetic US Acquisition Ordering'
        ds.SeriesDescription = 'Acquisition order phantom'
        ds.SeriesNumber = 1
        ds.InstanceNumber = number
        ds.Modality = 'US'
        ds.ImageType = ['ORIGINAL', 'PRIMARY']
        ds.TimezoneOffsetFromUTC = '+0000'
        for key, value in record.items():
            setattr(ds, key, value)
        ds.Rows = ds.Columns = 32
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.BitsAllocated = ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.WindowCenter = 128
        ds.WindowWidth = 256
        ds.PixelData = bytes([number * 20]) * 1024
        ds.save_as(ds.filename, enforce_file_format=True)
    print('Ascending InstanceNumber order: 4, 5, 2, 8, 1, 3, 6, 7')
    print('Descending from original order: 3, 1, 2, 8, 5, 4, 6, 7')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
