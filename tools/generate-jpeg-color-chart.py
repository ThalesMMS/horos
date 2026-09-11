#!/usr/bin/env python3
"""Generate a synthetic six-patch JPEG chart for local conversion tests (requires FFmpeg)."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


def generate(output):
    if output.exists():
        raise ValueError('Choose a new output file')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg must be on PATH')
    colors = [(220,30,40), (20,200,60), (30,70,220),
              (220,200,20), (180,30,190), (20,180,190)]
    with tempfile.TemporaryDirectory(prefix='horos-color-chart-') as folder:
        ppm = Path(folder)/'chart.ppm'
        ppm.write_bytes(b'P6\n192 128\n255\n' + b''.join(
            bytes(colors[(y//64)*3+x//64]) for y in range(128) for x in range(192)))
        subprocess.run([ffmpeg, '-v', 'error', '-i', str(ppm), '-q:v', '1', str(output)], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jpeg', type=Path)
    generate(parser.parse_args().jpeg)
