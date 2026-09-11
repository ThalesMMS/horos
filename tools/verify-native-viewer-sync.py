#!/usr/bin/env python3
"""Verify the documented A294 native MR sequence; screenshots need visual review."""
import argparse
import json
from pathlib import Path
import re


# label, mode, key viewer, A/B zero-based indices, layout
CASES = [
    ('loc-start', 3, 'B', 0, 0, 'columns'),
    ('loc-wheel-b', 3, 'B', 1, 1, 'columns'),
    ('loc-key-a', 3, 'A', 2, 2, 'columns'),
    ('loc-two-rows', 3, 'A', 2, 2, 'rows'),
    ('loc-drag-b', 3, 'B', 5, 5, 'rows'),
    ('abs-wheel-b', 1, 'B', 6, 6, 'rows'),
    ('abs-key-a', 1, 'A', 5, 5, 'rows'),
    ('abs-drag-b', 1, 'B', 6, 6, 'rows'),
    ('ratio-wheel-b', 4, 'B', 7, 7, 'rows'),
    ('ratio-key-a', 4, 'A', 8, 8, 'rows'),
    ('ratio-drag-b', 4, 'B', 4, 4, 'rows'),
    ('off-offset', 0, 'B', 4, 6, 'rows'),
    ('rel-start', 2, 'B', 4, 6, 'rows'),
    ('rel-wheel-b', 2, 'B', 5, 7, 'rows'),
    ('rel-key-a', 2, 'A', 6, 8, 'rows'),
    ('rel-drag-b', 2, 'B', 2, 4, 'rows'),
    ('loc-retiled-b', 3, 'B', 3, 3, 'columns'),
    ('loc-retiled-a', 3, 'A', 3, 3, 'columns'),
    ('gl-end', 3, 'A', 3, 3, 'columns'),
    ('metal-start', 3, 'B', 3, 3, 'columns'),
    ('metal-two-rows', 3, 'B', 3, 3, 'rows'),
    ('metal-wheel-b', 3, 'B', 4, 4, 'rows'),
    ('metal-key-a', 3, 'A', 5, 5, 'rows'),
    ('metal-drag-b', 3, 'B', 8, 8, 'rows'),
    ('gl-restored', 3, 'B', 8, 8, 'columns'),
]
TITLES = {'A': 'Crossref Axial Pair A (5)', 'B': 'Crossref Axial Pair B (6)'}
IDENTITY = ('controller', 'windowNumber', 'pixList', 'roiList')


def verify(folder):
    baseline = None
    for label, mode, key, index_a, index_b, layout in CASES:
        state = json.loads((folder / (label + '.json')).read_text())
        assert len(state['viewers']) == 2, label + ': requires two viewers'
        viewers = {v['title'].strip(): v for v in state['viewers']}
        assert set(viewers) == set(TITLES.values()), label + ': wrong series'
        pair = [viewers[TITLES[k]] for k in ('A', 'B')]
        identities = [tuple(v[k] for k in IDENTITY) for v in pair]
        if baseline is None:
            baseline = identities
            for i, field in enumerate(IDENTITY):
                assert identities[0][i] != identities[1][i], label + ': shared ' + field
        assert identities == baseline, label + ': viewer/volume identity changed'
        assert state['syncMode'] == mode, label + ': wrong sync mode'
        assert state['systemTabbing'] == 'always', label + ': global tabbing precondition'
        assert state['automaticTabbing'] is False, label + ': automatic tabs enabled'
        assert state['closeBeforeOpen'] is False, label + ': close-before-open enabled'
        assert state['screenCount'] == 1, label + ': this sequence uses one screen'
        assert state['keyWindow'].strip() == TITLES[key], label + ': wrong focused window'
        for which, v, expected in zip(('A', 'B'), pair, (index_a, index_b)):
            assert v['key'] == (which == key), label + ': key-window flag mismatch'
            assert v['visible'] and not v['miniaturized'], label + ': hidden viewer'
            assert v['tabbedCount'] == 0 and v['tabGroupCount'] == 1, label + ': grouped tabs'
            assert v['pixCount'] == 16 and not v['flippedData'], label + ': wrong fixture order'
            assert v['currentImage'] == expected, label + ': index mismatch in ' + which
            assert abs(v['location'] - expected) < 1e-6, label + ': location mismatch'
            if label.startswith('metal-') or label in ('gl-end', 'gl-restored'):
                assert v['metalEnabled'] == label.startswith('metal-'), label + ': wrong renderer'
                assert not v['fallback'], label + ': renderer fallback'
            if label in ('metal-wheel-b', 'metal-drag-b'):
                assert v['lastMetalCommandMilliseconds'] > 0, label + ': no completed Metal command'
            if label == 'gl-restored':
                assert v['currentTool'] == 0, label + ': Contrast tool not restored'
        if 'drag' in label:
            assert pair[1]['currentTool'] == 4, label + ': Scroll tool not selected'
        ax, ay, aw, ah = pair[0]['frame']
        bx, by, bw, bh = pair[1]['frame']
        assert min(aw, ah, bw, bh) > 0, label + ': empty window'
        assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay, label + ': overlapping viewers'
        if layout == 'columns':
            assert ay == by and ah == bh and ax != bx, label + ': expected columns'
        else:
            assert ax == bx and aw == bw and ay != by, label + ': expected rows'
        # Evidence of the focused viewer agrees with the separate process read.
        # Presence/signature is not a substitute for looking at the image.
        if label != 'loc-start':
            ax_state = (folder / (label + '.ax.txt')).read_text()
            assert ax_state.splitlines()[0].startswith('Window: "' + TITLES[key]), label + ': AX focus'
            slider = re.search(r'\bslider \(settable, float\) (\d+)', ax_state)
            expected_key_index = index_a if key == 'A' else index_b
            assert slider and int(slider[1]) == expected_key_index, label + ': AX index'
            signature = (folder / (label + '.jpg')).read_bytes()[:3]
            assert signature == b'\xff\xd8\xff', label + ': missing JPEG evidence'
        print('PASS', label)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    try:
        verify(args.folder)
    except (AssertionError, KeyError, OSError, ValueError) as error:
        raise SystemExit('FAIL: ' + str(error))
    print(f'PASS: {len(CASES)} native snapshots; review screenshots separately')
