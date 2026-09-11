#!/usr/bin/env python3
"""Check the documented native 2:1 synthetic phantom on a 14x17 portrait film."""
import argparse
import json
from pathlib import Path
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('capture', type=Path)
args = parser.parse_args()
capture = json.loads((args.capture/'received.json').read_text())
assert len(capture['film_boxes']) == len(capture['images']) == capture['actions'] == 1
film = capture['film_boxes'][0]
assert film['ImageDisplayFormat'] == 'STANDARD\\1,1'
assert film['FilmSizeID'] == '14INX17IN' and film['FilmOrientation'] == 'PORTRAIT'
image = np.load(args.capture/'image-001.npy')
assert np.array_equal(image, np.load(args.capture/'baseline.npy'))
y, x = np.nonzero(image)
width, height = int(x.max()-x.min()+1), int(y.max()-y.min()+1)
assert width == image.shape[1], 'Phantom must occupy the full raster width'
assert abs(height-width/2) <= 1, '2:1 phantom aspect ratio changed'
assert abs(int(y.min())-(image.shape[0]-1-int(y.max()))) <= 1, 'Unequal vertical margins'
print(f'PASS: 14x17 portrait 1x1, exact prepared pixels, full width {width}, content height {height}, aspect {width/height:.6f}, centered margins')
print('Physical fit estimate only: 14 inches wide and approximately 7 inches high; no physical printer calibration claim')
