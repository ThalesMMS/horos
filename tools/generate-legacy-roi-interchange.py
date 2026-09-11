#!/usr/bin/env python3
"""Write a ROI interchange JSON (#233 format) for a source CT series (#377 B).

The document references the real Study/Series/Frame of Reference and SOP
Instance UIDs of the given slices, so the SEG Surfaces panel can convert it
through the legacy ROI converter and match it to the open volume. It draws a
closed polygon (a 10 mm square rotated 45 degrees) on the middle slices and a
brush disc on the following ones, in image pixels, so the derived SEG has two
regions with known analytic areas.

    local-validation/venv/bin/python tools/generate-legacy-roi-interchange.py \
        ../DICOM_Example/local-validation/<fixture>/source-ct out.json
"""
import argparse
import base64
import json
from pathlib import Path

import pydicom

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='folder with the source CT slices')
parser.add_argument('output', type=Path)
parser.add_argument('--study', help='override StudyInstanceUID to produce a mismatching document')
args = parser.parse_args()
slices = []
for path in sorted(args.source.iterdir()):
    if path.is_file() and not path.name.startswith('.'):
        slices.append(pydicom.dcmread(str(path), stop_before_pixels=True))
if not slices:
    raise SystemExit('no slices found')
normal = None
slices.sort(key=lambda ds: float(ds.ImagePositionPatient[2]))
first = slices[0]
rows, columns = int(first.Rows), int(first.Columns)
images = []
polygon_slices = range(len(slices) // 4, len(slices) // 2)
brush_slices = range(len(slices) // 2, (3 * len(slices)) // 4)
cx, cy = columns / 2.0, rows / 2.0
brush_w = brush_h = max(4, columns // 4)
brush = bytearray()
for y in range(brush_h):
    for x in range(brush_w):
        dx, dy = x + 0.5 - brush_w / 2.0, y + 0.5 - brush_h / 2.0
        brush.append(1 if dx * dx + dy * dy <= (brush_w / 2.0) ** 2 else 0)
for index, ds in enumerate(slices):
    rois = []
    if index in polygon_slices:
        half = max(3.0, columns / 6.0)
        rois.append({'name': 'Legacy polygon', 'type': 'closed polygon', 'typeCode': 11,
                     'points': [[cx + half, cy], [cx, cy + half], [cx - half, cy], [cx, cy - half]],
                     'color': [0.9, 0.1, 0.9], 'thickness': 1, 'opacity': 1})
    if index in brush_slices:
        rois.append({'name': 'Legacy brush', 'type': 'brush', 'typeCode': 20, 'points': [],
                     'color': [0.1, 0.9, 0.9], 'thickness': 1, 'opacity': 1,
                     'brush': {'width': brush_w, 'height': brush_h,
                               'originX': int(cx - brush_w / 2), 'originY': int(cy - brush_h / 2),
                               'maskBase64': base64.b64encode(bytes(brush)).decode('ascii')}})
    images.append({'index': index, 'temporalIndex': 0, 'sopInstanceUID': str(ds.SOPInstanceUID), 'frame': 0,
                   'instanceNumber': int(getattr(ds, 'InstanceNumber', index + 1)),
                   'rows': rows, 'columns': columns,
                   'pixelSpacing': [float(ds.PixelSpacing[1]), float(ds.PixelSpacing[0])],
                   'sliceThickness': float(ds.SliceThickness),
                   'sliceLocation': float(ds.ImagePositionPatient[2]),
                   'imagePositionPatient': [float(v) for v in ds.ImagePositionPatient],
                   'imageOrientationPatient': [float(v) for v in ds.ImageOrientationPatient],
                   'rois': rois})
document = {'format': 'org.horosproject.roi-interchange', 'version': 1,
            'generator': 'tools/generate-legacy-roi-interchange.py',
            'coordinateSystems': {'pixel': 'image pixels: x right, y down, origin at the top-left corner of pixel (0,0), one unit per pixel',
                                  'patient': 'DICOM patient coordinates (LPS), millimetres'},
            'series': {'studyInstanceUID': args.study or str(first.StudyInstanceUID),
                       'seriesInstanceUID': str(first.SeriesInstanceUID),
                       'frameOfReferenceUID': str(first.FrameOfReferenceUID),
                       'modality': str(first.Modality), 'seriesDescription': str(getattr(first, 'SeriesDescription', ''))},
            'images': images}
args.output.write_text(json.dumps(document, indent=1) + '\n')
polygon_area = 2 * (max(3.0, columns / 6.0)) ** 2 * float(first.PixelSpacing[0]) * float(first.PixelSpacing[1])
print(json.dumps({'output': str(args.output), 'images': len(images), 'polygonSlices': len(polygon_slices),
                  'brushSlices': len(brush_slices), 'polygonAreaMm2': polygon_area,
                  'brushPixels': sum(brush)}))
