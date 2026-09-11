#!/usr/bin/env python3
"""Check local native #373/A255 snapshots against the analytic synthetic CT.

Inputs are produced through the native UI and read-only debugger snapshots;
this verifier does not drive the app or recreate the capture being verified.
No image, database or screenshot is written to the repository.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import sys


def verify(folder):
    def state(name):
        return json.loads((folder/(name+'.json')).read_text())

    def pixels(name):
        raw = (folder/(name+'.volume.f32')).read_bytes()
        assert len(raw) == 8*512*512*4, f'{name}: wrong volume dimensions'
        values = array('f')
        values.frombytes(raw)
        if sys.byteorder != 'little':
            values.byteswap()
        return values

    before = pixels('brush-before')
    after = pixels('brush-after')
    restored = pixels('brush-restored')
    table_count = patient_count = 0
    for i, (original, changed, reloaded) in enumerate(zip(before, after, restored)):
        y, x = divmod(i % (512*512), 512)
        expected = -1000
        if ((x-256)/150)**2 + ((y-216)/110)**2 <= 1:
            expected = 700
        if ((x-256)/142)**2 + ((y-216)/102)**2 <= 1:
            expected = 40
        table = 400 <= y < 432 and 96 <= x < 416
        if table:
            expected = 200
        assert original == expected, f'voxel {i}: input is not the CT phantom'
        assert changed == (-1000 if table else original), f'voxel {i}: wrong crop'
        assert reloaded == original, f'voxel {i}: reload did not restore source'
        table_count += table
        patient_count += expected in (40, 700)
    assert table_count == 81920 and patient_count == 414440

    roi = state('metal-roi')
    assert roi['metalEnabled'] and roi['fallback'] == ''
    assert roi['rois'] == [{'max':40, 'mean':40, 'min':40, 'name':'Unnamed', 'type':6}]
    assert (folder/'metal-initial.f32').read_bytes() == (folder/'metal-roi.f32').read_bytes()
    initial_mask = state('brush-before')
    assert [r['name'] for r in initial_mask['rois'] if r['type'] == 20] == ['A255 Patient Mask']
    assert all(names.count('A255 Patient Mask') == 1 for names in initial_mask['volumeROIs'])
    modified = state('brush-after-session')
    reloaded = state('brush-restored')
    assert modified['sessionID'] != reloaded['sessionID']
    assert reloaded['generation'] == modified['generation'] + 1
    for snapshot in (initial_mask, modified, reloaded):
        assert snapshot['metalEnabled'] and snapshot['fallback'] == ''
        assert snapshot['width'] == snapshot['height'] == 512
    disabled = (folder/'brush-no-selection.ax.txt').read_text()
    for title in ('Inside ROIs', 'Outside ROIs', 'ROIs with same name as the selected ROI', 'All ROIs'):
        assert f'radio button (disabled) {title},' in disabled

    hashes = json.loads((folder/'fixture-hashes.json').read_text())
    assert len(hashes) == 8
    for name, digest in hashes.items():
        assert Path(name).name == name
        assert hashlib.sha256((folder/'ct-table'/name).read_bytes()).hexdigest() == digest
    print(f'PASS: native Metal host; {table_count} table voxels removed; {patient_count} patient voxels preserved; '
          'all 2097152 voxels restored; session renewed; disabled selection controls; 8 original hashes intact')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshots', type=Path)
    verify(parser.parse_args().snapshots)
