#!/usr/bin/env python3
"""Decode every JPEG from a native export of the fixed memory fixture."""
import argparse
import shutil
import subprocess
from pathlib import Path


def verify(root):
    files = sorted(root.rglob('*.jpg'))
    assert len(files) == 256, len(files)
    assert len({p.parent for p in files}) == 1
    assert [p.name for p in files] == [f'IM-0001-{i:04d}.jpg' for i in range(1, 257)]
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg must be on PATH')
    pixels = subprocess.check_output([ffmpeg, '-v', 'error', '-pattern_type', 'glob',
        '-i', str(files[0].parent/'*.jpg'), '-f', 'rawvideo', '-pix_fmt', 'gray', '-'])
    assert len(pixels) == 256*512*512, len(pixels)
    for index in range(256):
        values = [pixels[index*512*512+y*512+x] for x, y in
                  [(128, 128), (384, 128), (128, 384), (384, 384)]]
        expected = [40+(index % 4)*35, 200, 100, 20]
        assert all(abs(a-b) <= 2 for a, b in zip(values, expected)), (index, values)
    print(f'PASS {root.name}: 256 decoded 512x512 JPEG, distinct sequential names, expected frame patterns')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    verify(parser.parse_args().directory)
