#!/usr/bin/env python3
"""Small synthetic RGB and calibrated MONOCHROME1 multiframe fixtures.

Four distinguishable frames per instance. RGB interleaved and planar encode
the same channels; MONOCHROME1 uses signed stored values and slope/intercept.
Keep generated DICOMs local and import copies into an isolated test database.
"""
import argparse
from pathlib import Path

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('destination', type=Path)
a = p.parse_args()
a.destination.mkdir(parents=True, exist_ok=True)
if any(a.destination.iterdir()):
    p.error('destination must be empty')
study, frame_of_reference = generate_uid(), generate_uid()
y, x = np.mgrid[:64, :64]
for number, name in enumerate(('rgb-interleaved', 'rgb-planar', 'mono1-calibrated'), 1):
    color = name.startswith('rgb')
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = ('1.2.840.10008.5.1.4.1.1.7.4' if color
                      else '1.2.840.10008.5.1.4.1.1.7.3')
    ds.SOPInstanceUID, ds.SeriesInstanceUID = generate_uid(), generate_uid()
    ds.StudyInstanceUID, ds.FrameOfReferenceUID = study, frame_of_reference
    ds.PatientName, ds.PatientID = 'QA^Planar Formats', 'S373-FORMATS'
    ds.PatientBirthDate, ds.PatientSex = '19700101', 'O'
    ds.StudyDate, ds.StudyTime, ds.StudyID = '20260913', '120000', '373'
    ds.StudyDescription, ds.SeriesDescription = 'Synthetic planar format matrix', name
    ds.SeriesNumber, ds.InstanceNumber, ds.Modality = number, 1, 'OT'
    ds.ImageType = ['DERIVED', 'SECONDARY']
    ds.ConversionType, ds.BurnedInAnnotation = 'WSD', 'NO'
    ds.NumberOfFrames, ds.FrameTime, ds.FrameIncrementPointer = 4, 100, 0x00181063
    ds.Rows, ds.Columns = 64, 64
    ds.ImagePositionPatient, ds.ImageOrientationPatient = [12, 24, 36], [1, 0, 0, 0, 1, 0]
    ds.PixelSpacing, ds.SliceThickness = [0.8, 0.5], 2
    ds.SamplesPerPixel, ds.PhotometricInterpretation = (3, 'RGB') if color else (1, 'MONOCHROME1')
    ds.BitsAllocated, ds.BitsStored, ds.HighBit = (8, 8, 7) if color else (16, 12, 11)
    ds.PixelRepresentation = 0 if color else 1
    if color:
        ds.PlanarConfiguration = int(name == 'rgb-planar')
        frames = np.stack([np.stack(((3*x+29*f)%256, (4*y+17*f)%256,
                                     (x+2*y+43*f)%256), axis=-1) for f in range(4)]).astype('u1')
        ds.PixelData = (frames.transpose(0, 3, 1, 2) if ds.PlanarConfiguration else frames).tobytes()
        ds.WindowCenter, ds.WindowWidth = 127.5, 255
    else:
        frames = np.stack([x+2*y+101*f-1024 for f in range(4)]).astype('<i2')
        ds.PixelData = frames.tobytes()
        ds.RescaleSlope, ds.RescaleIntercept, ds.RescaleType = 2, -100, 'US'
        ds.WindowCenter, ds.WindowWidth = -1600, 1200
    ds.save_as(a.destination/(name+'.dcm'), enforce_file_format=True)
    print(name, ds.SeriesInstanceUID)
