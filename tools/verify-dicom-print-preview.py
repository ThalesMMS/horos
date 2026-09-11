#!/usr/bin/env python3
"""Verify the documented four-image native preview scenario, using local captures."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('capture', type=Path)
parser.add_argument('source_hashes', type=Path, help='Pre-test JSON mapping local source paths to SHA-256')
args = parser.parse_args()
received = json.loads((args.capture / 'received.json').read_text())
assert received['actions'] == 1
assert [image['position'] for image in received['images']] == [1, 2, 3, 4]
assert [image['referenced_position'] for image in received['images']] == [1, 2, 3, 4]
assert received['film_boxes'][0]['ImageDisplayFormat'] == 'STANDARD\\2,2'
baselines = [np.load(args.capture / f'baseline-{i:03}.npy') for i in range(1, 5)]
images = [np.load(args.capture / f'image-{i:03}.npy') for i in range(1, 5)]
assert all(a.shape == b.shape for a, b in zip(images, baselines))
h, w = images[0].shape
rotated = np.rot90(baselines[0], 2)
for yf, xf in [(0.375, 0.375), (0.375, 0.625), (0.625, 0.375), (0.625, 0.625)]:
    y, x = int(h*yf), int(w*xf)
    assert images[0][y, x] == rotated[y, x]
    sy, sx = int((y-h/2)*2+h/2), int((x-w/2)*2+w/2)
    assert images[1][y, x] == baselines[1][sy, sx]
assert not np.any(images[1][:h//4-2])
assert not np.any(images[1][3*h//4+2:])
assert not np.any(images[1][:, :w//4-2])
assert not np.any(images[1][:, 3*w//4+2:])
assert np.array_equal(images[2][h//3:2*h//3, w//3:2*w//3], baselines[2][h//3:2*h//3, w//3:2*w//3])
assert np.count_nonzero(images[2] != baselines[2]) > 100
assert np.array_equal(images[3], baselines[3])
hashes = json.loads(args.source_hashes.read_text())
assert hashes and all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in hashes.items())
delta = np.abs(images[0].astype(int) - rotated.astype(int))
print(f'PASS: ordered tiles, 180-degree orientation, half-size zoom, annotations, exact unedited tile and {len(hashes)} unchanged source hashes')
print(f'Rotation edge rasterization: {np.count_nonzero(delta)} differing pixels, maximum absolute delta {delta.max()} (not an exact-pixel rotation claim)')
