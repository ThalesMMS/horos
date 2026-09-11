#!/usr/bin/env python3
"""Check native JPEG/TIFF exports of generate-jpeg-series-fixture.py (requires FFmpeg)."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path


def verify(root, browser, format="jpg"):
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('ffmpeg and ffprobe must be on PATH')
    files = sorted(root.rglob('*.' + format))
    assert len(files) == 8, f'Expected eight {format} files, got {len(files)}'
    groups = {}
    for path in files:
        key = path.parent if browser else path.name.rsplit('.', 2)[0]
        groups.setdefault(key, []).append(path)
    assert len(groups) == 2, f'Expected two series, got {len(groups)}'
    for group, paths in groups.items():
        assert len(paths) == 4, f'{group}: expected four frames'
        for index, path in enumerate(sorted(paths)):
            expected_suffix = f'-{index + 1:04d}.{format}' if browser else f'.{index + 1:04d}.{format}'
            assert path.name.endswith(expected_suffix), path.name
            stream = json.loads(subprocess.check_output([
                ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(path)
            ]))['streams'][0]
            width, height = stream['width'], stream['height']
            assert width == height and width >= 64, (path, width, height)
            if browser:
                assert (width, height) == (64, 64)
            pixels = subprocess.check_output([
                ffmpeg, '-v', 'error', '-i', str(path), '-f', 'rawvideo',
                '-pix_fmt', 'gray', '-'
            ])
            assert len(pixels) == width * height
            # Interior samples avoid annotation overlays and interpolation edges.
            values = [pixels[int(height*y)*width+int(width*x)] for x, y in
                      [(0.35, 0.35), (0.65, 0.35), (0.35, 0.65), (0.65, 0.65)]]
            expected = [40 + index*35, 200, 100, 20]
            if format == "tif":
                # Exact 8-bit display levels for this fixture (WW 256, WL 128).
                expected = [40, 75, 110, 144][index:index+1] + [199, 100, 20]
            assert all(abs(a-b) <= (2 if format == "jpg" else 0) for a, b in zip(values, expected)), (path, values)
            print(f'{path.relative_to(root)}: {width}x{height}, quadrants {values}')
    print('PASS: two series, four ordered frames each, asymmetric orientation retained')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--browser', action='store_true', help='Check hierarchical database export')
    parser.add_argument('--format', choices=['jpg', 'tif'], default='jpg')
    args = parser.parse_args()
    verify(args.directory, args.browser, args.format)
