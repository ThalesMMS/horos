#!/usr/bin/env python3
"""Compare the captures of tools/capture-native-seg-surfaces.py (#377 A).

Tolerances fixed before looking at the pixels:
- every owned view (2D, the three MPR planes, VR) must change when all
  surfaces are hidden: at least MIN_CHANGED pixels differ by more than
  DIFF (max channel difference, 0-255);
- the foreign viewer (another series) must not change at all;
- of the changed pixels in the visible capture, at least COLOUR_FRACTION must be
  within COLOUR_DISTANCE (Euclidean, 0-255 per channel) of one of the segment
  colours read from the panel snapshots, blended over the hidden pixel (opacity 1
  lines are drawn over the image, VR actors are lit so their shade varies);
- the capture after undo must match the visible capture on at least
  RESTORE_FRACTION of the pixels within DIFF.

    local-validation/venv/bin/python tools/compare-native-seg-surfaces.py
"""
import argparse
import json
from pathlib import Path

import numpy as np

MIN_CHANGED, DIFF, COLOUR_FRACTION, COLOUR_DISTANCE, RESTORE_FRACTION = 40, 24, 0.80, 80.0, 0.995
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input', type=Path, default=Path('local-validation/issue-377-native'))
parser.add_argument('--visible', default='visible')
parser.add_argument('--hidden', default='hidden')
parser.add_argument('--restored', default='restored')
parser.add_argument('--output', type=Path, default=Path('docs/seg-surface-native-results.json'))
parser.add_argument('--import-label', default='import-seg', help='report of the import step whose timing and diagnosis are copied')
parser.add_argument('--views', default='twoD,mpr1,mpr2,mpr3,vrView,other', help='which captures must exist (after closing MPR/VR only twoD,other remain)')
args = parser.parse_args()


def load(label, name):
    meta = json.loads((args.input / (label + '.json')).read_text())
    if name not in meta:
        return None, meta
    m = meta[name]
    raw = np.fromfile(args.input / (label + '.' + name + '.rgb'), dtype=np.uint8)
    return raw.reshape(m['height'], m['width'], m['spp'])[:, :, :3].astype(np.int16), meta


def ppm(path, image):
    with open(path, 'wb') as f:
        f.write(b'P6\n%d %d\n255\n' % (image.shape[1], image.shape[0]))
        f.write(np.clip(image, 0, 255).astype(np.uint8).tobytes())


visible_meta = json.loads((args.input / (args.visible + '.json')).read_text())
colours = np.array([[s['red'], s['green'], s['blue']] for s in visible_meta['surfaces']]) * 255.0
results = {'tolerances': {'minChanged': MIN_CHANGED, 'maxChannelDiff': DIFF, 'colourFraction': COLOUR_FRACTION,
                          'colourDistance': COLOUR_DISTANCE, 'restoreFraction': RESTORE_FRACTION},
           'segmentColours': colours.tolist(), 'views': {}}
ok = True
for name in args.views.split(','):
    vis, _ = load(args.visible, name)
    hid, _ = load(args.hidden, name)
    res, _ = load(args.restored, name)
    if vis is None or hid is None:
        results['views'][name] = {'status': 'missing'}; ok = False; continue
    if vis.shape != hid.shape:
        results['views'][name] = {'status': 'shape mismatch', 'visible': vis.shape, 'hidden': hid.shape}; ok = False; continue
    changed = np.abs(vis - hid).max(axis=2) > DIFF
    count = int(changed.sum())
    entry = {'size': [int(vis.shape[1]), int(vis.shape[0])], 'changedPixels': count}
    if name == 'other':
        entry['status'] = 'pass' if count == 0 else 'fail: foreign viewer changed'
    else:
        if count > 0:
            ys, xs = np.nonzero(changed)
            entry['changedBox'] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
            pixels = vis[changed].astype(np.float64)
            # Nearest segment colour, allowing VR shading (scaled colour) and line antialiasing.
            best = np.full(len(pixels), np.inf)
            for colour in colours:
                for shade in (1.0, 0.85, 0.7, 0.55, 0.4):
                    best = np.minimum(best, np.linalg.norm(pixels - colour * shade, axis=1))
            near = float((best <= COLOUR_DISTANCE).mean())
            entry['colourFraction'] = near
            mean = pixels.mean(axis=0)
            entry['meanChangedColour'] = [float(v) for v in mean]
            entry['status'] = 'pass' if count >= MIN_CHANGED and near >= COLOUR_FRACTION else 'fail: changed pixels do not carry the segment colours'
        else:
            entry['status'] = 'fail: no overlay drawn'
        if res is not None and res.shape == vis.shape:
            same = float((np.abs(vis - res).max(axis=2) <= DIFF).mean())
            entry['restoredAgreement'] = same
            if same < RESTORE_FRACTION:
                entry['status'] = 'fail: undo did not restore the drawing'
        diff = np.zeros_like(vis); diff[changed] = vis[changed]
        ppm(args.input / (name + '.visible.ppm'), vis); ppm(args.input / (name + '.hidden.ppm'), hid); ppm(args.input / (name + '.diff.ppm'), diff)
    ok = ok and entry['status'] == 'pass'
    results['views'][name] = entry
results['overall'] = 'pass' if ok else 'fail'
results['import'] = {k: v for k, v in json.loads((args.input / (args.import_label + '.json')).read_text()).items() if k in ('bytes', 'diagnosis', 'importMilliseconds')}
results['surfaces'] = visible_meta['surfaces']
args.output.write_text(json.dumps(results, indent=1) + '\n')
for name, entry in results['views'].items():
    print(name, entry.get('status'), 'changed', entry.get('changedPixels'), 'colour', entry.get('colourFraction'), 'restored', entry.get('restoredAgreement'))
print('overall', results['overall'])
raise SystemExit(0 if ok else 1)
