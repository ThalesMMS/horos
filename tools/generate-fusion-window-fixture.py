#!/usr/bin/env python3
"""Generate registered CT/PT volumes with distinct intensities and WL/WW defaults."""
import argparse
import uuid
from pathlib import Path
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, PositronEmissionTomographyImageStorage, ExplicitVRLittleEndian


def uid(value):
    return '2.25.' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'urn:horos:fusion-window:ct-pt:' + value).int)


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    for number, name, center, width in [(1, 'Fusion CT Primary', 100, 200),
                                       (2, 'Fusion PT Secondary', 600, 400)]:
        for z in range(16):
            sop_class = CTImageStorage if number == 1 else PositronEmissionTomographyImageStorage
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = sop_class
            meta.MediaStorageSOPInstanceUID = uid(f'image-{number}-{z}')
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds = FileDataset(str(output / f'{number:02d}-{z:02d}.dcm'), {}, file_meta=meta, preamble=b'\0' * 128)
            ds.SOPClassUID = sop_class
            ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
            ds.StudyInstanceUID = uid('study')
            ds.SeriesInstanceUID = uid(f'series-{number}')
            ds.FrameOfReferenceUID = uid('frame')
            ds.PatientName = 'QA^Fusion CT PT'
            ds.PatientID = 'LOCAL-FUSION-CT-PT'
            ds.StudyID = 'FUSIONWL'
            ds.StudyDescription = 'Fusion Window Acceptance'
            ds.SeriesDescription = name
            ds.StudyDate = ds.SeriesDate = ds.ContentDate = '20260908'
            ds.StudyTime = ds.SeriesTime = ds.ContentTime = '120000'
            ds.Modality = 'CT' if number == 1 else 'PT'
            ds.RescaleSlope = 1
            ds.RescaleIntercept = 0
            ds.RescaleType = 'HU' if number == 1 else 'CNTS'
            if number == 2:
                ds.Units = 'CNTS'
                ds.SeriesType = ['STATIC', 'IMAGE']
                ds.CountsSource = 'EMISSION'
                ds.CorrectedImage = ['NONE']
                ds.DecayCorrection = 'NONE'
            ds.SeriesNumber = number
            ds.InstanceNumber = z + 1
            ds.ImageType = ['ORIGINAL', 'PRIMARY', 'OTHER']
            ds.Rows = ds.Columns = 32
            ds.PixelSpacing = [1, 1]
            ds.SliceThickness = ds.SpacingBetweenSlices = 1
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.ImagePositionPatient = [0, 0, z]
            ds.SliceLocation = z
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = 'MONOCHROME2'
            ds.PixelRepresentation = 0
            ds.BitsAllocated = ds.BitsStored = 16
            ds.HighBit = 15
            ds.WindowCenter = center
            ds.WindowWidth = width
            values = [x + 2*y + 3*z if number == 1 else 500 + 3*x + y + 5*z
                      for y in range(32) for x in range(32)]
            ds.PixelData = b''.join(value.to_bytes(2, 'little') for value in values)
            ds.save_as(ds.filename, enforce_file_format=True)
    print('Generated 32 CT/PT images: registered primary/secondary volumes, WL/WW 100/200 and 600/400.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
