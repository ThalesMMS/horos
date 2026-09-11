#!/usr/bin/env python3
"""Verify the synthetic naming fixture after native ordinary or anonymous export."""
from pathlib import Path
import argparse
import hashlib
import re
from collections import Counter
import pydicom

parser = argparse.ArgumentParser()
parser.add_argument('fixture', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--anonymous', action='store_true')
args = parser.parse_args()
inputs = list(args.fixture.glob('*.dcm'))
outputs = list(args.output.rglob('*.dcm'))
assert len(inputs) == len(outputs) == 5, 'Expected five DICOM instances'
def pixel_key(dataset):
    return (int(dataset.Rows), int(dataset.Columns), int(getattr(dataset, 'NumberOfFrames', 1)), hashlib.sha256(dataset.PixelData).hexdigest())
source_datasets = [pydicom.dcmread(path) for path in inputs]
output_datasets = [pydicom.dcmread(path) for path in outputs]
assert Counter(map(pixel_key, source_datasets)) == Counter(map(pixel_key, output_datasets)), 'Pixel data or frame counts changed'
assert sum(int(getattr(d, 'NumberOfFrames', 1)) for d in output_datasets) == 8
series_paths = {path.parent for path in outputs}
assert len(series_paths) == 2, 'Homonymous series must occupy separate folders'
if args.anonymous:
    pattern = re.compile(r'Anonymized-[0-9A-F-]{36}/Study-\d+/Series-\d+/IM-[0-9-]+\.dcm')
    for path in outputs:
        assert pattern.fullmatch(path.relative_to(args.output).as_posix()), 'Anonymous path contains unexpected metadata'
else:
    source_hashes = {str(d.SOPInstanceUID): hashlib.sha256(path.read_bytes()).hexdigest() for path, d in zip(inputs, source_datasets)}
    for path, dataset in zip(outputs, output_datasets):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source_hashes[str(dataset.SOPInstanceUID)], 'Source bytes changed'
        parts = path.relative_to(args.output).parts
        assert len(parts) == 4
        assert parts[0].startswith('QA_FOLDER_126-')
        assert parts[1].startswith('Study-')
        assert parts[2].startswith('Same_Series-')
print('PASS: five instances, eight preserved frames, two separate series folders' + ('; generic anonymous paths' if args.anonymous else '; Patient ID and study fallback; byte-identical files'))
