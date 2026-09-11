#!/usr/bin/env python3
"""Measure the name cells of the captures from capture-native-browser-rows.py (#380, A300).

A painted row is a study row whose `patientUID` equals the selected study's and
is not the selected row itself — exactly what
`-[BrowserController outlineView:willDisplayCell:...]` paints, `previousItem`
being the selection.

The captures keep the alpha channel, so each painted cell is composited twice,
over a white and over a black backdrop. That is the whole of A300: a cell that
writes a translucent *text* colour takes the colour of whatever is behind it,
and over a dark backdrop that is the black band covering the name; an opaque
background reads the same over either backdrop.

Tolerances, fixed before looking at any pixel:

- the painted background must read the same over both backdrops, within
  BACKDROP luminance, in every appearance and every action;
- it must keep a luminance separation of at least SEPARATION from the glyphs
  over both backdrops;
- the before captures — the same list on a build with the two fix hunks
  reverted — must violate at least one of those, or the comparison proves
  nothing.

    local-validation/venv/bin/python tools/compare-native-browser-rows.py
"""
import argparse
import json
from pathlib import Path

import numpy as np

SEPARATION, BACKDROP = 0.40, 0.05
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input', type=Path, default=Path('local-validation/issue-380-native'))
parser.add_argument('--output', type=Path, default=Path('docs/browser-row-background-results.json'))
args = parser.parse_args()


def load(label):
    meta = json.loads((args.input / (label + '.json')).read_text())
    raw = np.fromfile(args.input / (label + '.raw'), dtype=np.uint8)
    rows, stride, spp = meta['height'], meta['bytesPerRow'], meta['samplesPerPixel']
    image = raw[:rows * stride].reshape(rows, stride)[:, :meta['width'] * spp].reshape(rows, meta['width'], spp)
    return meta, image[:, :, :3].astype(np.float64) / 255.0, image[:, :, 3]


def painted_rows(meta):
    uid = meta.get('selectedPatientUID') or ''
    selected = meta.get('selectedRow')
    return [row for row in meta['visibleRows']
            if row.get('type') == 'Study' and len(row.get('patientUID') or '') > 1
            and row['patientUID'] == uid and row['row'] != selected]


def measure(label):
    meta, image, alpha = load(label)
    scale = meta.get('renderScale') or 1
    name_width = next(c['width'] for c in meta['columns'] if c['id'] == 'name')
    dark_mode = 'Dark' in meta['appearance']
    measured = 0
    over_white, over_black, separations = [], [], []
    for row in painted_rows(meta):
        x, y, _, h = row['rect']
        top, bottom = int(round(y * scale)), int(round((y + h) * scale))
        left, right = int(round(x * scale)), int(round((x + name_width) * scale))
        top, bottom = max(0, top), min(image.shape[0], bottom)
        left, right = max(0, left), min(image.shape[1], right)
        if bottom - top < 2 or right - left < 2:
            continue
        rgb = image[top:bottom, left:right]
        a = alpha[top:bottom, left:right].astype(np.float64)[:, :, None] / 255.0
        measured += 1
        for backdrop, sink in ((1.0, over_white), (0.0, over_black)):
            # The capture is premultiplied: colour + backdrop * (1 - alpha).
            composited = rgb + backdrop * (1.0 - a)
            luminance = 0.2126 * composited[:, :, 0] + 0.7152 * composited[:, :, 1] + 0.0722 * composited[:, :, 2]
            background = float(np.median(luminance))
            glyph = float(np.percentile(luminance, 99 if dark_mode else 1))
            sink.append(background)
            separations.append(abs(background - glyph))
    if not measured:
        return {'label': label, 'appearance': meta['appearance'], 'before': meta['before'], 'renderScale': scale,
                'size': [meta['width'], meta['height']], 'rowsTotal': meta['rows'], 'paintedRowsMeasured': 0,
                'clean': False}
    swing = max(abs(w - b) for w, b in zip(over_white, over_black))
    separation = min(separations)
    return {'label': label, 'appearance': meta['appearance'], 'before': meta['before'], 'renderScale': scale,
            'size': [meta['width'], meta['height']], 'rowsTotal': meta['rows'], 'paintedRowsMeasured': measured,
            'overWhite': [min(over_white), max(over_white)], 'overBlack': [min(over_black), max(over_black)],
            'backdropSwing': swing, 'separation': separation,
            'clean': swing <= BACKDROP and separation >= SEPARATION}


results = {'tolerances': {'minimumSeparation': SEPARATION, 'maximumBackdropSwing': BACKDROP},
           'note': 'before = a build with the two hunks of the A300 fix reverted, captured on the same list, same window and same database',
           'captures': []}
labels = sorted(p.stem for p in args.input.glob('*.json') if (args.input / (p.stem + '.raw')).exists())
ok = True
for label in labels:
    entry = measure(label)
    results['captures'].append(entry)
    if entry['before']:
        entry['verdict'] = ('fail: the pre-fix build looks the same, so the capture proves nothing'
                            if entry['clean'] else 'reproduces the defect')
        ok = ok and not entry['clean']
    else:
        entry['verdict'] = 'pass' if entry['clean'] else 'fail: the painted cell is backdrop-dependent or covers the name'
        ok = ok and entry['clean']
results['overall'] = 'pass' if ok else 'fail'
args.output.write_text(json.dumps(results, indent=1) + '\n')
for entry in results['captures']:
    if not entry.get('paintedRowsMeasured'):
        print('%-24s %-10s no painted row drawn' % (entry['label'], entry['appearance'].replace('NSAppearanceName', '')))
        continue
    print('%-24s %-10s rows %2d  over white %.3f  over black %.3f  swing %.3f  separation %.3f  %s'
          % (entry['label'], entry['appearance'].replace('NSAppearanceName', ''), entry['paintedRowsMeasured'],
             entry['overWhite'][0], entry['overBlack'][0], entry['backdropSwing'], entry['separation'], entry['verdict']))
print('overall', results['overall'])
raise SystemExit(0 if ok else 1)
