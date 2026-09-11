#!/usr/bin/env python3
"""Native MONOCHROME1 regression, JSON round trip and rejecting bad evidence.

Pass the private capture directory and its fixture manifest. A clean clone
does not contain these inputs, so this check exits 2 when they are absent.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--captures', type=Path)
p.add_argument('--manifest', type=Path)
p.add_argument('--exports', type=Path)
a = p.parse_args()
if not all((a.captures, a.manifest, a.exports)):
    print('needs --captures, --manifest and --exports plus pydicom/numpy')
    raise SystemExit(2)
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('format_oracle', root/'tools/verify-native-planar-format.py')
oracle = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(oracle)
except ModuleNotFoundError as error:
    print('needs Python dependency:', error.name)
    raise SystemExit(2)
manifest = json.loads(a.manifest.read_text())
cases = [('mono1-metal-roi0',0,'metal'), ('mono1-metal-measured1',1,'metal'),
         ('mono1-metal-measured2',2,'metal'), ('mono1-metal-measured3',3,'metal'),
         ('mono1-original-measured0',0,'original'), ('mono1-original-measured3',3,'original'),
         ('mono1-rois-roundtrip',0,'original')]
results = [oracle.verify(a.captures/(name+'.json'),manifest,True,frame,backend,True)
           for name,frame,backend in cases]

# Restore an explicitly seeded legacy cache, then save a different calibrated
# window through the UI and close/reopen its viewer. The positive stored level
# is the existing database contract, not the live calibrated level.
storage_cases = [('mono1-storage-restored', 'original', -1888, 512),
                 ('mono1-storage-new-reopened', 'metal', -1952, 400)]
for name, backend, level, width in storage_cases:
    path = a.captures/(name+'.json')
    state = json.loads(path.read_text())
    assert state['level'] == level and state['widthWindow'] == width, 'saved window changed'
    assert state['storedSeriesLevel'] == -level and state['storedSeriesWidth'] == width, 'legacy cache domain changed'
    results.append(oracle.verify(path, manifest, True, 0, backend))

# The native baseline must fail for its wrong calibrated samples, rather than
# merely lacking a newer collector field or the expected ROI.
try:
    oracle.verify(a.captures/'mono1-roi-before.json',manifest)
except AssertionError as error:
    assert str(error).startswith('native sample mismatch:'), str(error)
else:
    raise AssertionError('accepted the native sign-inverted baseline')

export = json.loads((a.exports/'mono1-exported.json').read_text())
again = json.loads((a.exports/'mono1-reexported.json').read_text())
for value in (export, again):
    value.pop('created',None)
assert export == again, 'round trip changed ROI geometry, identity or properties'
assert len(export['images']) == 4
for frame, image in enumerate(export['images']):
    assert image.get('frame',0) == frame and image.get('temporalIndex',0) == 0
    assert len(image['rois']) == 1 and image['rois'][0]['name'] == 'S373-MONO1-F'+str(frame)
    assert image['rois'][0]['rect'] == [16,16,16,16]
cleared = json.loads((a.captures/'mono1-rois-cleared.json').read_text())
assert all(not f['rois'] for f in cleared['frames']), 'round trip was imported over existing ROIs'

base_path = a.captures/'mono1-metal-roi0.json'
base = json.loads(base_path.read_text())
def wrong_sample(state, directory):
    path = directory/state['frames'][0]['file']
    data = bytearray(path.read_bytes());data[3] ^= 0x80;path.write_bytes(data)
def wrong_output(state, directory):
    (directory/'check.bgra').write_bytes(bytes((base_path.with_suffix('.bgra')).stat().st_size))
def wrong_clut(state, directory):
    (directory/'check.clut').write_bytes(bytes(1024))
controls = {
    'sample sign':wrong_sample, 'presented pixels':wrong_output, 'CLUT':wrong_clut,
    'missing frame':lambda s,d:s['frames'].pop(),
    'duplicate frame':lambda s,d:s['frames'].append(copy.deepcopy(s['frames'][0])),
    'wrong SOP':lambda s,d:s['frames'][0].update(sop='1.2.3'),
    'wrong spacing':lambda s,d:s['frames'][0].update(spacing=[1,1]),
    'wrong display frame':lambda s,d:s.update(currentImage=1),
    'wrong backend':lambda s,d:s.update(metalEnabled=False),
    'unexpected fallback':lambda s,d:s.update(fallback='Unavailable'),
    'wrong window':lambda s,d:s.update(level=1600),
    'wrong polarity':lambda s,d:s['frames'][0].update(displayInverted=False),
    'wrong ROI value':lambda s,d:s['frames'][0]['rois'][0].update(mean=2004),
    'wrong ROI association':lambda s,d:s['frames'][0]['rois'][0].update(name='S373-MONO1-F1'),
}
with tempfile.TemporaryDirectory(prefix='horos-format-controls-') as temporary:
    directory = Path(temporary)
    for name, mutate in controls.items():
        for frame in base['frames']:
            shutil.copyfile(a.captures/frame['file'],directory/frame['file'])
        for suffix in ('.bgra','.clut'):
            shutil.copyfile(base_path.with_suffix(suffix),directory/('check'+suffix))
        state = copy.deepcopy(base);mutate(state,directory)
        path = directory/'check.json';path.write_text(json.dumps(state))
        try:
            oracle.verify(path,manifest,True,0,'metal',True)
        except (AssertionError,KeyError,ValueError):
            pass
        else:
            raise AssertionError('accepted '+name)
print(json.dumps({'nativeCases':len(results),'samples':sum(r['samples'] for r in results),
                  'presentationPixels':sum(r['presentationPixels'] for r in results),
                  'maximumChannelError':max(r['maximumChannelError'] for r in results),
                  'nativeBaselineRejected':True,'negativeControls':len(controls),'roiRoundTrip':True,
                  'storedWindowCases':len(storage_cases)},indent=2))
