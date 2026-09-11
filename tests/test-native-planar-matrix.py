#!/usr/bin/env python3
"""Native RGB, palette, JPEG 2000 and 4D evidence; private fixtures required."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--captures', type=Path)
p.add_argument('--manifest', type=Path)
p.add_argument('--exports', type=Path)
a = p.parse_args()
if not all((a.captures, a.manifest, a.exports)):
    print('needs --captures, --manifest and --exports plus pydicom/numpy/openjpeg')
    raise SystemExit(2)
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('oracle', root/'tools/verify-native-planar-format.py')
oracle = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(oracle)
except ModuleNotFoundError as error:
    print('needs Python dependency:', error.name)
    raise SystemExit(2)
manifest = json.loads(a.manifest.read_text())
cases = [('rgb-interleaved-frame0', 0), ('rgb-interleaved-frame3', 3),
         ('rgb-planar-final0', 0), ('rgb-planar-final3', 3)]
cases += [('matrix-palette-'+name, 0) for name in
          ('8bit', '16bit-narrow', '16bit-wide', '16bit-pixels', 'offset', 'us-cine')]
cases += [('matrix-palette-cine-last', 7)]
cases += [('matrix-tomo-'+route+'-'+edge, frame)
          for route in ('local', 'wado') for edge, frame in (('first', 0), ('last', 7))]
results = {name: oracle.verify(a.captures/(name+'.json'), manifest, True, frame)
           for name, frame in cases}
for time in range(3):
    name = 'matrix-temporal-t'+str(time)
    state = json.loads((a.captures/(name+'.json')).read_text())
    assert (state['level'], state['widthWindow']) == (150, 400), 'temporal window changed'
    results[name] = oracle.verify(a.captures/(name+'.json'), manifest, True, 0,
                                 'metal', False, time, True)

cleared = json.loads((a.captures/'matrix-temporal-cleared.json').read_text())
assert len(cleared['frames']) == 24 and all(not f['rois'] for f in cleared['frames'])
original = json.loads((a.exports/'temporal-exported.json').read_text())
again = json.loads((a.exports/'temporal-reexported.json').read_text())
for value in (original, again):
    value.pop('created', None)
assert original == again, 'temporal JSON geometry, identity or properties changed'
assert len(original['images']) == 3
records = {r['path']: r for r in manifest['files']}
for time, image in enumerate(original['images']):
    assert image.get('temporalIndex', 0) == time and image['index'] == 0
    assert image['sopInstanceUID'] == records[f'temporal/t{time:02d}-z00.dcm']['sop']
    assert len(image['rois']) == 1 and image['rois'][0]['typeCode'] == 6

base_path = a.captures/'matrix-temporal-t0.json'
base = json.loads(base_path.read_text())
def wrong_sample(s, d):
    path = d/s['frames'][0]['file']
    data = bytearray(path.read_bytes()); data[3] ^= 0x80; path.write_bytes(data)
controls = {
    'calibrated sample': wrong_sample,
    'missing whole time': lambda s,d: s.update(frames=[f for f in s['frames'] if f['movie'] != 2], movies=2),
    'time association': lambda s,d: s['frames'][0].update(movie=1),
    'displayed time': lambda s,d: s.update(currentMovie=1),
    'ROI value': lambda s,d: s['frames'][0]['rois'][0].update(mean=150),
    'ROI association': lambda s,d: s['frames'][0].update(rois=[]),
    'spacing': lambda s,d: s['frames'][0].update(spacing=[2,1]),
    'fallback': lambda s,d: s.update(fallback='Unavailable'),
    'backend': lambda s,d: s.update(metalEnabled=False),
    'pixels': lambda s,d: (d/'check.bgra').write_bytes(bytes(base_path.with_suffix('.bgra').stat().st_size)),
}
with tempfile.TemporaryDirectory(prefix='horos-format-matrix-') as tmp:
    directory = Path(tmp)
    for name, mutate in controls.items():
        for frame in base['frames']:
            shutil.copyfile(a.captures/frame['file'], directory/frame['file'])
        for suffix in ('.bgra', '.clut'):
            shutil.copyfile(base_path.with_suffix(suffix), directory/('check'+suffix))
        state = copy.deepcopy(base); mutate(state, directory)
        path = directory/'check.json'; path.write_text(json.dumps(state))
        try:
            oracle.verify(path, manifest, True, 0, 'metal', False, 0, True)
        except (AssertionError, KeyError, ValueError):
            pass
        else:
            raise AssertionError('accepted '+name)

for record in manifest['files']:
    source = Path(manifest['root'])/record['path']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == record['sha256'], 'fixture changed'
print(json.dumps({'nativeCases': len(results), 'cases': results,
                  'sampleChecks': sum(r['samples'] for r in results.values()),
                  'presentationPixels': sum(r['presentationPixels'] for r in results.values()),
                  'maximumChannelError': max(r['maximumChannelError'] for r in results.values()),
                  'temporalJSONRoundTrip': True, 'negativeControls': len(controls),
                  'preservedOriginalFiles': len(manifest['files'])}, indent=2))
