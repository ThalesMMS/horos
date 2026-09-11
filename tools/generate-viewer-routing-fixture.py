#!/usr/bin/env python3
"""Generate three synthetic MR volumes for multi-viewer command routing acceptance."""
import argparse
from pathlib import Path
import uuid
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import MRImageStorage, ExplicitVRLittleEndian

def uid(name):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:viewer-routing:' + name).int)

def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    names = ['Routing Alpha', 'Routing Beta', 'Routing Gamma']
    for number, name in enumerate(names, 1):
        for image in range(1, 17):
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = MRImageStorage
            meta.MediaStorageSOPInstanceUID = uid(f'image-{number}-{image}')
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds = FileDataset(str(output/f'{number:02d}-{image:02d}.dcm'), {}, file_meta=meta, preamble=b'\0'*128)
            ds.SOPClassUID = MRImageStorage
            ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
            ds.PatientName = 'QA^Viewer Routing'
            ds.PatientID = 'LOCAL-VIEWER-ROUTING'
            ds.StudyInstanceUID = uid('study')
            ds.SeriesInstanceUID = uid(f'series-{number}')
            ds.FrameOfReferenceUID = uid('frame')
            ds.StudyDate = ds.SeriesDate = ds.AcquisitionDate = ds.ContentDate = '20260907'
            ds.StudyTime = ds.SeriesTime = ds.AcquisitionTime = ds.ContentTime = '120000'
            ds.StudyID = 'ROUTING'
            ds.StudyDescription = 'Viewer Routing Acceptance'
            ds.SeriesDescription = name
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
            ds.SpacingBetweenSlices = 1
            ds.SliceLocation = image-1
            ds.AcquisitionNumber = 1
            ds.WindowCenter = 200
            ds.WindowWidth = 400
            ds.PixelData = b''.join((number*60+image*3+x+y).to_bytes(2,'little') for y in range(32) for x in range(32))
            ds.save_as(ds.filename, enforce_file_format=True)
    print('Study UID:', uid('study'))
    print('Three 16-slice axial volumes, 1 mm spacing; distinct intensity ramps.')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    generate(parser.parse_args().output)
