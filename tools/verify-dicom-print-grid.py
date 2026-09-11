#!/usr/bin/env python3
"""Verify native 24/30-image Print SCP captures against pre-send baselines."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('grid24', type=Path)
parser.add_argument('grid30', type=Path)
parser.add_argument('rejected', type=Path)
args = parser.parse_args()
for directory, count, layout in [(args.grid24,24,'STANDARD\\6,4'), (args.grid30,30,'STANDARD\\6,5')]:
    capture = json.loads((directory/'received.json').read_text())
    assert len(capture['film_boxes']) == 1
    assert capture['film_boxes'][0]['ImageDisplayFormat'] == layout
    assert len(capture['images']) == count and capture['actions'] == 1
    for index, image in enumerate(capture['images'],1):
        assert image['position'] == image['referenced_position'] == index
        before = np.load(directory/f'baseline-{index:03}.npy')
        after = np.load(directory/f'image-{index:03}.npy')
        assert np.array_equal(before,after), index
    print(f'PASS: {count} ordered images exactly match prepared baselines; one Print action')
rejected = json.loads((args.rejected/'received.json').read_text())
assert len(rejected['film_boxes']) == 1 and rejected['film_boxes'][0]['ImageDisplayFormat'] == 'STANDARD\\6,5'
assert not rejected['images'] and rejected['actions'] == 0
hashes = json.loads((args.grid24/'source-hashes.json').read_text())
assert hashes and all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == value for path,value in hashes.items())
print(f'PASS: rejected Film Box sent no images/actions; {len(hashes)} original files unchanged')
