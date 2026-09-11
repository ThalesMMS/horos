#!/usr/bin/env python3
"""A111 native captures and deliberately corrupted controls; private data required."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--captures',type=Path)
parser.add_argument('--matrix',type=Path)
args=parser.parse_args()
if args.captures is None or args.matrix is None:
    print('SKIP: supply --captures PRIVATE_DIRECTORY --matrix MANIFEST.json')
    raise SystemExit(2)
try:
    import numpy as np
except ImportError:
    print('SKIP: use a Python environment with numpy')
    raise SystemExit(2)
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('presentation',root/'tools/verify-native-planar-presentation.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
matrix=json.loads(args.matrix.read_text())
assert len(matrix)==len({row['capture'] for row in matrix}), 'Duplicate capture'
totals=[oracle.verify(args.captures/(row['capture']+'.json'),row['case']) for row in matrix]
by_case={row['case']:row['capture'] for row in matrix}
needed={'pt-mean','pt-shutter','pt-gaussian-roi','fusion-gray','gray-control'}
assert needed <= by_case.keys(), 'Required negative-control inputs are missing'

def corrupt_bytes(folder,state,suffix,layer=0):
    path=folder/(state['layers'][layer]['prefix']+suffix)
    if suffix=='.rgba':
        data=np.fromfile(path,np.uint8).reshape(256,4)
        if layer: data[:,3]=128
        else: data[1,0]^=1
    else:
        data=np.fromfile(path,'<f4');data[0]+=1
    data.tofile(path)

def native_pixel(folder,state,foreign):
    w,h=state['viewSize']
    path=folder/'capture.bgra';pixels=np.fromfile(path,np.uint8).reshape(h,w,4)
    pixels[h//2,w//2,:3]=[3,2,1] if foreign else [0,0,0]
    pixels.tofile(path)

def shift_one_pixel(folder,state):
    layer=state['layers'][0];p=layer['screenToPixel'];delta=(p[2]-p[0])/state['viewSize'][0]
    for i in (0,2,4):p[i]+=delta

controls=[
    ('volume voxel','pt-mean',lambda f,s:corrupt_bytes(f,s,'.volume.f32')),
    ('current voxel','pt-mean',lambda f,s:corrupt_bytes(f,s,'.f32')),
    ('texture upload','pt-mean',lambda f,s:corrupt_bytes(f,s,'.texture.f32')),
    ('palette','pt-mean',lambda f,s:corrupt_bytes(f,s,'.rgba')),
    ('color outside CLUT','pt-mean',lambda f,s:native_pixel(f,s,True)),
    ('wrong valid CLUT color','pt-mean',lambda f,s:native_pixel(f,s,False)),
    ('one screen pixel displacement','pt-shutter',shift_one_pixel),
    ('wrong projection mode','pt-mean',lambda f,s:s['layers'][0].update(stackMode=2)),
    ('missing Metal fallback','pt-mean',lambda f,s:s.update(fallback='')),
    ('wrong modality','pt-mean',lambda f,s:s['layers'][0].update(modality='NM')),
    ('changed ROI mean','pt-gaussian-roi',lambda f,s:s['layers'][0]['rois'][0].update(mean=2056)),
    ('wrong secondary WL','fusion-gray',lambda f,s:s['layers'][1].update(level=601)),
    ('wrong fusion alpha','fusion-gray',lambda f,s:corrupt_bytes(f,s,'.rgba',1)),
    ('wrong fusion factor','fusion-gray',lambda f,s:s.update(blendingFactor=64)),
    ('missing shutter pixels','pt-shutter',lambda f,s:(f/(s['layers'][0]['prefix']+'.u8')).write_bytes(bytes(256*256))),
]
for name,case,mutate in controls:
    source=args.captures/(by_case[case]+'.json')
    state=json.loads(source.read_text())
    with tempfile.TemporaryDirectory(prefix='horos-a111-negative-') as directory:
        folder=Path(directory)
        shutil.copyfile(source.with_suffix('.bgra'),folder/'capture.bgra')
        for layer in state['layers']:
            for path in args.captures.glob(layer['prefix']+'.*'):
                shutil.copyfile(path,folder/path.name)
        mutate(folder,state)
        capture=folder/'capture.json';capture.write_text(json.dumps(state))
        try:
            with contextlib.redirect_stdout(io.StringIO()):oracle.verify(capture,case)
        except AssertionError:
            print('REJECTED:',name)
        else:
            raise AssertionError('Accepted corruption: '+name)
# The pre-fix native primary must remain a failing control. A permissive
# composite tolerance must never hide its cropped texture coordinate.
try:
    oracle.verify(args.captures/'exploratory-gray-control.json','gray-control')
except AssertionError:
    print('REJECTED: native gray before geometry correction')
else:
    raise AssertionError('Accepted the original native geometry defect')
print(f'PASS: {len(matrix)} captures, {sum(x[0] for x in totals)} pixels, '
      f'{sum(x[1] for x in totals)} exact calibrated voxels; {len(controls)+1} negative controls rejected')
