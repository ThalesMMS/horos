#!/usr/bin/env python3
"""Generate a fixed 256-image, 512x512 synthetic study for batch memory measurements."""
import argparse
import runpy
from pathlib import Path


def generate(output):
    fixture = runpy.run_path(str(Path(__file__).with_name('generate-jpeg-series-fixture.py')))
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    uid = fixture['uid']
    for index in range(256):
        path = output / f'{index:04d}.dcm'
        ds = fixture['dataset'](path, f'memory-512-256-{index}', False)
        ds.PatientName = 'QA^JPEGMemory'
        ds.PatientID = 'LOCAL-JPEG-MEMORY-512-256'
        ds.StudyInstanceUID = uid('memory-512-256-study')
        ds.SeriesInstanceUID = uid('memory-512-256-series')
        ds.StudyDescription = ds.SeriesDescription = 'JPEG Memory 512 256'
        ds.StudyID = 'JPEGMEMORY'
        ds.Rows = ds.Columns = 512
        ds.InstanceNumber = index + 1
        ds.PixelData = (bytes([40 + (index % 4)*35])*256 + bytes([200])*256)*256 + (bytes([100])*256 + bytes([20])*256)*256
        ds.save_as(path, enforce_file_format=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
