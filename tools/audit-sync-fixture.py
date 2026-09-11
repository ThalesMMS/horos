#!/usr/bin/env python3
"""Summarize geometric/type multiplicities in a DICOM ZIP without extracting images."""
import argparse, collections, hashlib, json
from pathlib import Path
import zipfile
import pydicom

def audit(path):
    series = collections.defaultdict(list)
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            if item.is_dir() or item.filename.startswith('__MACOSX/') or '/._' in item.filename:
                continue
            try:
                with archive.open(item) as stream:
                    image = pydicom.dcmread(stream, stop_before_pixels=True)
            except pydicom.errors.InvalidDicomError:
                continue
            if 'SeriesInstanceUID' in image and 'ImagePositionPatient' in image:
                series[str(image.SeriesInstanceUID)].append(image)
    result = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'series': []}
    # Do not include patient identity, UIDs, dates or free-text descriptions in the report.
    for images in series.values():
        positions = collections.defaultdict(list)
        types = collections.Counter()
        for image in images:
            kind = '\\'.join(str(v) for v in image.get('ImageType', []))
            types[kind] += 1
            positions[tuple(float(v) for v in image.ImagePositionPatient)].append(kind)
        result['series'].append({
            'images': len(images), 'unique_positions': len(positions),
            'position_multiplicity': dict(collections.Counter(len(v) for v in positions.values())),
            'image_types': dict(types),
            'positions_with_distinct_types': sum(len(set(v)) > 1 for v in positions.values()),
        })
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.zip), indent=2, sort_keys=True))
