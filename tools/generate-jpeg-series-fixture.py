#!/usr/bin/env python3
"""Generate matching single-instance and multiframe grayscale export fixtures."""
import argparse,uuid
from pathlib import Path
from pydicom.dataset import FileDataset,FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian,SecondaryCaptureImageStorage,MultiFrameGrayscaleByteSecondaryCaptureImageStorage

def uid(name):return '2.25.'+str(uuid.uuid5(uuid.NAMESPACE_URL,'horos-jpeg-series-'+name).int)
def frame(index):
    # Large asymmetric interior patches remain measurable behind viewer overlays.
    return bytes((40+index*35 if x<32 and y<32 else 200 if x>=32 and y<32 else 100 if x<32 else 20) for y in range(64) for x in range(64))
def dataset(path,name,multi):
    sop=MultiFrameGrayscaleByteSecondaryCaptureImageStorage if multi else SecondaryCaptureImageStorage
    meta=FileMetaDataset();meta.MediaStorageSOPClassUID=sop;meta.MediaStorageSOPInstanceUID=uid(name);meta.TransferSyntaxUID=ExplicitVRLittleEndian
    ds=FileDataset(str(path),{},file_meta=meta,preamble=b'\0'*128)
    ds.SOPClassUID=sop;ds.SOPInstanceUID=meta.MediaStorageSOPInstanceUID
    ds.PatientName='QA^JPEGSeries';ds.PatientID='LOCAL-JPEG-SERIES';ds.PatientBirthDate='';ds.PatientSex='O'
    ds.StudyInstanceUID=uid('study');ds.StudyDescription='JPEG Series Acceptance';ds.StudyID='JPEGTEST';ds.StudyDate='20260908';ds.StudyTime='120000'
    ds.SeriesInstanceUID=uid('multi' if multi else 'single');ds.SeriesNumber=2 if multi else 1
    ds.SeriesDescription='JPEG Multi Frame' if multi else 'JPEG Single Frames';ds.Modality='OT';ds.ConversionType='WSD';ds.Manufacturer='Synthetic fixture'
    ds.Rows=ds.Columns=64;ds.SamplesPerPixel=1;ds.PhotometricInterpretation='MONOCHROME2';ds.BitsAllocated=ds.BitsStored=8;ds.HighBit=7;ds.PixelRepresentation=0
    ds.WindowCenter=128;ds.WindowWidth=256;ds.ImageType=['DERIVED','SECONDARY'];ds.ContentDate='20260908';ds.ContentTime='120000';ds.PatientOrientation=['L','P']
    return ds

def generate(output):
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('Use an empty output directory')
    for i in range(4):
        p=output/f'single-{i}.dcm';ds=dataset(p,f'single-{i}',False);ds.InstanceNumber=i+1;ds.PixelData=frame(i);ds.save_as(p,enforce_file_format=True)
    p=output/'multi.dcm';ds=dataset(p,'multi-image',True);ds.InstanceNumber=1;ds.NumberOfFrames=4;ds.FrameTime=100;ds.FrameIncrementPointer=[0x00181063];ds.PixelData=b''.join(frame(i) for i in range(4));ds.save_as(p,enforce_file_format=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);generate(parser.parse_args().output)
