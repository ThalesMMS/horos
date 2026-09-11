#!/usr/bin/env python3
"""Generate three synthetic patients for custom PatientName annotation acceptance."""
import argparse
from pathlib import Path
import uuid
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import MRImageStorage, ExplicitVRLittleEndian

def uid(name):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:patient-annotation:' + name).int)

def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    names = ['QA^Annotation Alice', 'QA^Annotation Beatrice', None]
    for number, name in enumerate(names, 1):
        for image in range(1, 3):
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = MRImageStorage
            meta.MediaStorageSOPInstanceUID = uid(f'image-{number}-{image}')
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds = FileDataset(str(output/f'{number:02d}-{image:02d}.dcm'), {}, file_meta=meta, preamble=b'\0'*128)
            ds.SOPClassUID = MRImageStorage
            ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
            if name is not None:
                ds.PatientName = name
            ds.Manufacturer = 'QA Annotation Manufacturer'
            ds.PatientID = f'LOCAL-ANNOTATION-{number}'
            ds.StudyInstanceUID = uid(f'study-{number}')
            ds.SeriesInstanceUID = uid(f'series-{number}')
            ds.FrameOfReferenceUID = uid('frame')
            ds.StudyDate = ds.SeriesDate = ds.AcquisitionDate = ds.ContentDate = '20260907'
            ds.StudyTime = ds.SeriesTime = ds.AcquisitionTime = ds.ContentTime = '120000'
            ds.StudyID = f'ANNO{number}'
            ds.StudyDescription = f'Patient Annotation Acceptance {number}'
            ds.SeriesDescription = f'Annotation Case {number}'
            ds.SeriesNumber = number
            ds.InstanceNumber = image
            ds.Modality = 'MR'
            ds.ImageType = ['ORIGINAL', 'PRIMARY', 'OTHER']
            ds.Rows = ds.Columns = 32
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = 'MONOCHROME2'
            ds.BitsAllocated = ds.BitsStored = 16
            ds.HighBit = 15
            ds.PixelRepresentation = 0
            ds.PixelSpacing = [1, 1]
            ds.ImagePositionPatient = [0, 0, image-1]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.SliceThickness = 1
            ds.WindowCenter = 100
            ds.WindowWidth = 200
            ds.PixelData = (number*20+image).to_bytes(2,'little')*1024
            ds.save_as(ds.filename, enforce_file_format=True)
    for number, name in enumerate(names, 1):
        print(f'{number}: {name!r}, Study UID: {uid(f"study-{number}")}')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    generate(parser.parse_args().output)
