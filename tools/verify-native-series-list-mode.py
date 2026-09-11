#!/usr/bin/env python3
"""Check the native A273 snapshots described in series-list-mode-validation.md.

Snapshots contain only local inspection results, never DICOM data. This verifier
does not launch or drive the application and does not turn a missing run into a
pass. The native scenario uses two viewers on one physical screen; controlled
multi-screen tests are separate.
"""
import argparse
import json
from pathlib import Path

STEPS = {
    'native-initial-floating': (True, 8, 'B'),
    'native-docked': (False, 8, None),
    'native-floating-b': (True, 8, 'B'),
    'native-floating-a': (True, 8, 'A'),
    'native-floating-b-focus': (True, 8, 'B'),
    'native-docked-restored': (False, 8, None),
    'native-hidden': (False, 1, None),
    'native-shown': (False, 8, None),
    'native-after-close': (True, 8, 'A'),
}
IDENTITY = ('controller', 'windowNumber', 'matrix', 'scroll', 'pixList', 'roiList',
            'currentImage', 'title', 'pixCount', 'roiCount')


def verify(directory):
    baseline = None
    for name, (floating, rows, owner) in STEPS.items():
        state = json.loads((directory / (name + '.json')).read_text())
        assert state['screenCount'] == 1, f'{name}: expected the documented one-screen run'
        assert state['floating'] == floating and state['listVisible'], f'{name}: mode'
        viewers = {v['title'].strip(): v for v in state['viewers']}
        assert len(viewers) == (1 if name == 'native-after-close' else 2), f'{name}: viewer count'
        assert len({v['controller'] for v in viewers.values()}) == len(viewers), f'{name}: duplicate viewer'
        if baseline is None:
            baseline = viewers
            assert set(baseline) == {'Crossref Axial Pair A (5)', 'Crossref Axial Pair B (6)'}
        for title, view in viewers.items():
            for key in IDENTITY:
                assert view[key] == baseline[title][key], f'{name}: {title}: changed {key}'
            assert view['windowVisible'] and view['splitSubviews'] == 2, f'{name}: missing pane/window'
            assert view['rows'] == rows and len(view['cells']) >= rows, f'{name}: rows'
            assert view['dockHidden'] == floating, f'{name}: dock visibility'
            if rows == 8:
                # The renderer uses cell background colors to highlight the
                # current series; NSMatrix.selectedRow alone is not that state.
                assert [c['title'] for c in view['cells']] == [
                    c['title'] for c in baseline[title]['cells']
                ], f'{name}: series changed'
                series = title.rsplit(' (', 1)[0]
                current = next(c for c in view['cells'] if c['title'].splitlines()[0] == series)
                original = next(c for c in baseline[title]['cells'] if c['title'].splitlines()[0] == series)
                assert current['background'] == original['background'], f'{name}: current series highlight changed'
            else:
                assert 'Show Series' in view['cells'][0]['title'], f'{name}: missing restore header'
                # NSMatrix can retain blank cells beyond its current row count.
                assert all(not c['title'] for c in view['cells'][rows:]), f'{name}: uncleared spare cells'
            if not floating:
                assert view['matrixWindowClass'] == 'OSIWindow', f'{name}: list not returned to viewer'
        visible = [panel for panel in state['panels'] if panel['visible']]
        assert len(visible) == int(floating), f'{name}: duplicate or missing shared panel'
        if floating:
            view = viewers[f'Crossref Axial Pair {owner} ({5 if owner == "A" else 6})']
            panel = visible[0]
            assert panel['owner'] == view['controller'], f'{name}: wrong panel owner'
            assert panel['panelScroll'] == view['scroll'], f'{name}: wrong borrowed list'
            assert view['matrixWindowClass'] == 'ThumbnailsListNSWindow', f'{name}: wrong parent window'
        for panel in state['panels']:
            if panel['panelScreen'] >= state['screenCount']:
                assert not panel['visible'] and panel['owner'] == '0x0', f'{name}: spare panel claimed a viewer'
        if name in ('native-floating-a', 'native-floating-b-focus'):
            assert state['keyWindow'].strip() == view['title'].strip(), f'{name}: focus'
        if name in ('native-docked', 'native-floating-b', 'native-docked-restored'):
            assert state['keyWindow'] == 'Horos Preferences: Viewers', f'{name}: preference focus lost'
    print('PASS: nine native states; stable viewers/data/lists, Hide/Show highlights, '
          'one shared panel, A/B focus handoff, owner close and preference focus')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    verify(args.directory)
