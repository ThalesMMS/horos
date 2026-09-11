#!/usr/bin/env python3
"""Generate a local synthetic numbered print study; never uses patient data."""
import argparse
from pathlib import Path
import runpy
import numpy as np
from pydicom.uid import generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--count', type=int, choices=[24,30,35], default=30)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
if any(args.output.iterdir()): raise ValueError('Use an empty output directory')
fixture = runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))
study, series = generate_uid(), generate_uid()
segments = {'0':'abcdef','1':'bc','2':'abged','3':'abgcd','4':'fgbc','5':'afgcd','6':'afgecd','7':'abc','8':'abcdefg','9':'abfgcd'}
bars = {'a':(0,0,2,8),'b':(0,6,9,2),'c':(8,6,9,2),'d':(15,0,2,8),'e':(8,0,9,2),'f':(0,0,9,2),'g':(7,0,2,8)}
for index in range(args.count):
    path = args.output / f'print-{index+1:02}.dcm'
    ds = fixture['dataset'](path, f'print-native-{index}', False)
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.StudyInstanceUID, ds.SeriesInstanceUID = study, series
    suffix = '' if args.count == 30 else str(args.count)
    ds.PatientName = f'QA^PrintGrid{suffix}'; ds.PatientID = 'LOCAL-PRINT-GRID' + ('-' + suffix if suffix else '')
    ds.StudyID = 'PRINT162'; ds.StudyDescription = 'Numbered Print Grid Acceptance'
    ds.SeriesDescription = 'Numbered Print Phantom'; ds.SeriesNumber = 1
    ds.Rows, ds.Columns, ds.InstanceNumber = 32, 64, index+1
    pixels = np.full((32,64), 20+index*5, dtype=np.uint8)
    pixels[:4,:4] = 0; pixels[-4:,-4:] = 255
    for digit_index, digit in enumerate(f'{index+1:02}'):
        for segment in segments[digit]:
            dy, dx, height, width = bars[segment]
            y, x = 7+dy, 30+digit_index*12+dx
            pixels[y:y+height,x:x+width] = 255
    ds.PixelData = pixels.tobytes()
    ds.save_as(path, enforce_file_format=True)
print(f'Generated {args.count} synthetic numbered images')
