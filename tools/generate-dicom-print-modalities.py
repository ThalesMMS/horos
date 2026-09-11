#!/usr/bin/env python3
"""Generate synthetic US/CR print fixtures locally; no patient data or external input."""
import argparse
from pathlib import Path
import runpy
import numpy as np
from pydicom.uid import generate_uid, UltrasoundImageStorage, ComputedRadiographyImageStorage

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output',type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
if any(args.output.iterdir()): raise ValueError('Use an empty output directory')
base = runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))
for modality, sop, bits, rows, columns in [('US',UltrasoundImageStorage,8,96,128),('CR',ComputedRadiographyImageStorage,16,128,96)]:
    directory=args.output/modality;directory.mkdir()
    path=directory/'image.dcm';ds=base['dataset'](path,'print-'+modality,False)
    ds.SOPClassUID=ds.file_meta.MediaStorageSOPClassUID=sop
    ds.SOPInstanceUID=ds.file_meta.MediaStorageSOPInstanceUID=generate_uid()
    ds.StudyInstanceUID=generate_uid();ds.SeriesInstanceUID=generate_uid()
    ds.PatientName='QA^Print'+modality;ds.PatientID='LOCAL-PRINT-'+modality
    ds.StudyDescription='Print '+modality+' Acceptance';ds.StudyID='PRINT'+modality
    ds.SeriesDescription='Synthetic '+modality+' Print';ds.SeriesNumber=1;ds.InstanceNumber=1
    ds.Modality=modality;ds.Rows=rows;ds.Columns=columns
    ds.BitsAllocated=bits;ds.BitsStored=8 if bits==8 else 12;ds.HighBit=ds.BitsStored-1
    ds.PixelSpacing=[0.5,0.5];ds.ImageType=['ORIGINAL','PRIMARY']
    if modality=='CR': ds.ImagerPixelSpacing=[0.5,0.5];ds.BodyPartExamined='PHANTOM'
    maximum=(1<<ds.BitsStored)-1
    y,x=np.indices((rows,columns));pixels=(maximum*(x/(columns-1)*0.7+y/(rows-1)*0.3)).astype('u1' if bits==8 else '<u2')
    pixels[:8,:8]=maximum;pixels[-8:,-8:]=0
    ds.WindowCenter=(maximum+1)/2;ds.WindowWidth=maximum+1;ds.PixelData=pixels.tobytes()
    ds.save_as(path,enforce_file_format=True)
print('Generated synthetic US 8-bit landscape and CR 12-bit portrait fixtures')
