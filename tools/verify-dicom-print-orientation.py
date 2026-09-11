#!/usr/bin/env python3
"""Verify native 35-image portrait/landscape captures and calculate ideal cell margins."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('portrait', type=Path)
parser.add_argument('landscape', type=Path)
args = parser.parse_args()
for mode, directory, film_width, film_height in [('PORTRAIT',args.portrait,14,17), ('LANDSCAPE',args.landscape,17,14)]:
    capture = json.loads((directory/'received.json').read_text())
    assert len(capture['film_boxes']) == 1
    film = capture['film_boxes'][0]
    assert film['ImageDisplayFormat'] == 'STANDARD\\7,5'
    assert film['FilmSizeID'] == '14INX17IN' and film['FilmOrientation'] == mode
    assert len(capture['images']) == 35 and capture['actions'] == 1
    for index, metadata in enumerate(capture['images'],1):
        assert metadata['position'] == metadata['referenced_position'] == index
        image = np.load(directory/f'image-{index:03}.npy')
        assert np.array_equal(image,np.load(directory/f'baseline-{index:03}.npy'))
        assert np.array_equal(image,np.load(args.portrait/f'image-{index:03}.npy'))
        y,x = np.nonzero(image)
        content_width,content_height = int(x.max()-x.min()+1),int(y.max()-y.min()+1)
        assert content_width == image.shape[1] and abs(content_height-content_width/2) <= 1
        cell_width,cell_height = film_width/7,film_height/5
        scale = min(cell_width/image.shape[1],cell_height/image.shape[0])
        top = (cell_height-image.shape[0]*scale)/2 + int(y.min())*scale
        bottom = (cell_height-image.shape[0]*scale)/2 + (image.shape[0]-1-int(y.max()))*scale
        assert abs(top-bottom) <= scale*1.01
        assert abs(content_width*scale/(content_height*scale)-2) < 0.01
    print(f'PASS {mode}: 35 ordered exact arrays, correct film/layout, unchanged image orientation and aspect')
    print(f'Ideal cell inches {cell_width:.6f} x {cell_height:.6f}; content {content_width*scale:.6f} x {content_height*scale:.6f}; top/bottom {top:.6f}/{bottom:.6f}')
hashes = json.loads((args.portrait/'source-hashes.json').read_text())
assert hashes and all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path,digest in hashes.items())
print(f'PASS {len(hashes)} source hashes unchanged. Margins are calculated ideal fit, not physical printer calibration.')
