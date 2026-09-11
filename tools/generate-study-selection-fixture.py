#!/usr/bin/env python3
"""Generate three synthetic studies for one patient; requires pydicom."""
import argparse
from pathlib import Path
import uuid
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

def uid(name):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:study-selection:' + name).int)

def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    for number in range(1, 4):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage
        meta.MediaStorageSOPInstanceUID = uid(f'image-{number}')
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(str(output / f'{number}.dcm'), {}, file_meta=meta, preamble=b'\0'*128)
        ds.SOPClassUID = CTImageStorage
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.PatientName = 'QA^Study Selection'
        ds.PatientID = 'LOCAL-STUDY-SELECTION'
        ds.PatientBirthDate = '20000101'
        ds.StudyInstanceUID = uid(f'study-{number}')
        ds.SeriesInstanceUID = uid(f'series-{number}')
        ds.FrameOfReferenceUID = uid(f'frame-{number}')
        ds.StudyDate = ds.SeriesDate = ds.AcquisitionDate = ds.ContentDate = f'2026090{number}'
        ds.StudyTime = ds.SeriesTime = ds.AcquisitionTime = ds.ContentTime = '120000'
        ds.StudyID = f'SELECTION-{number}'
        ds.StudyDescription = f'Study selection {number}'
        ds.SeriesDescription = 'Selection target' if number == 1 else f'Selection sibling {number}'
        ds.Modality = 'CT'
        ds.SeriesNumber = ds.InstanceNumber = 1
        ds.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
        ds.Rows = ds.Columns = 32
        ds.PixelSpacing = [1, 1]
        ds.ImagePositionPatient = [0, 0, 0]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.SliceThickness = 1
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        ds.PixelData = (number*50).to_bytes(2, 'little')*1024
        ds.RescaleIntercept = 0
        ds.RescaleSlope = 1
        ds.WindowCenter = 100
        ds.WindowWidth = 200
        ds.save_as(ds.filename, enforce_file_format=True)
    print('Three studies, one patient, one image per study; target and two siblings')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
