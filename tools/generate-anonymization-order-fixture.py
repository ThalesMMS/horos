#!/usr/bin/env python3
"""Generate a synthetic CT stack whose filename order opposes its spatial order."""
import argparse
from pathlib import Path
import runpy
import numpy as np
from pydicom.uid import CTImageStorage,generate_uid

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('output',type=Path)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
if any(args.output.iterdir()): raise ValueError('Use an empty output directory')
base=runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))
study,series,frame=generate_uid(),generate_uid(),generate_uid()
for index in range(12):
    path=args.output/f'reverse-{99-index:02}.dcm';ds=base['dataset'](path,'order-'+str(index),False)
    ds.SOPClassUID=ds.file_meta.MediaStorageSOPClassUID=CTImageStorage
    ds.SOPInstanceUID=ds.file_meta.MediaStorageSOPInstanceUID=generate_uid()
    ds.StudyInstanceUID=study;ds.SeriesInstanceUID=series;ds.FrameOfReferenceUID=frame
    ds.PatientName='QA^AnonymizationOrder';ds.PatientID='LOCAL-ORDER-140'
    ds.StudyDescription='Anonymization Order Acceptance';ds.StudyID='ORDER140'
    ds.SeriesDescription='Known CT Spatial Order';ds.SeriesNumber=1;ds.InstanceNumber=index+1
    ds.Modality='CT';ds.ImageType=['ORIGINAL','PRIMARY','AXIAL']
    ds.Rows=ds.Columns=64;ds.BitsAllocated=16;ds.BitsStored=12;ds.HighBit=11
    ds.ImageOrientationPatient=[1,0,0,0,1,0];ds.ImagePositionPatient=[0,0,index*2.5]
    ds.PixelSpacing=[0.75,0.75];ds.SliceThickness=2.5;ds.SpacingBetweenSlices=2.5
    ds.SliceLocation=index*2.5;ds.PositionReferenceIndicator='';ds.PatientPosition='HFS'
    ds.RescaleIntercept=-1024;ds.RescaleSlope=1;ds.RescaleType='HU'
    ds.WindowCenter=0;ds.WindowWidth=2048
    pixels=np.full((64,64),100+index*150,dtype='<u2')
    pixels[8:16,8:8+3*(index+1)]=3000
    ds.PixelData=pixels.tobytes();ds.save_as(path,enforce_file_format=True)
print('Generated 12 CT slices: ascending instance/position, descending filenames')
