#!/usr/bin/env python3
"""Generate three synthetic DICOMs sharing InstanceNumber, with distinct pixels/UIDs."""
import argparse,importlib.util,tempfile
from pathlib import Path
from pydicom import dcmread

def generate(output):
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('Use an empty output directory')
    spec=importlib.util.spec_from_file_location('fusion',Path(__file__).with_name('generate-fusion-window-fixture.py'))
    fusion=importlib.util.module_from_spec(spec);spec.loader.exec_module(fusion)
    with tempfile.TemporaryDirectory() as temporary:
        source=Path(temporary)/'source';fusion.generate(source)
        for index in range(3):
            ds=dcmread(source/f'01-{index:02d}.dcm')
            ds.PatientName='QA^InstanceCollision';ds.PatientID='LOCAL-EXPORT-INSTANCE-COLLISION'
            ds.StudyDescription='Export Instance Collision';ds.StudyID='COLLISION'
            ds.SeriesDescription='Export Instance Collision';ds.InstanceNumber=1
            for keyword in ('StudyInstanceUID','SeriesInstanceUID','FrameOfReferenceUID'):
                setattr(ds,keyword,fusion.uid('export-instance-collision-'+keyword))
            ds.SOPInstanceUID=fusion.uid(f'export-instance-collision-image-{index}')
            ds.file_meta.MediaStorageSOPInstanceUID=ds.SOPInstanceUID
            ds.save_as(output/f'{index}.dcm',enforce_file_format=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    generate(parser.parse_args().output)
