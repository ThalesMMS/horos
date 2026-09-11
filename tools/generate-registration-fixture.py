#!/usr/bin/env python3
"""Two CT series of one synthetic patient related by a known rigid transform (#378).

Series A ("Registration fixed", Frame of Reference F1) is a 32×32×16 volume
with four bright marker cubes at distinct voxels and a tube. Series B
("Registration moving", Frame of Reference F2) holds the same voxels, but its
Image Position/Orientation are series A's carried by a rigid transform T
(10° about z, 5° about x, translation (5, −3, 2) mm), so voxel (i, j, k) is the
same physical marker in both and the landmark pairs are the marker centres.
The manifest records T (row-major, B patient frame = T · A patient frame),
the marker voxels and SHA-256 of every file.

    local-validation/venv/bin/python tools/generate-registration-fixture.py <empty dir>
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
out = args.output.resolve()
if out == root or root in out.parents:
    raise SystemExit('output must be outside the repository')
if out.exists() and any(out.iterdir()):
    raise SystemExit('output must be empty')
out.mkdir(parents=True, exist_ok=True)

rows = columns = 32
frames = 16
spacing = (1.0, 1.0, 2.0)
origin = np.array([-16.0, -16.0, -16.0])
markers = [(4, 5, 2), (26, 6, 5), (8, 25, 9), (24, 24, 13)]  # (column, row, slice)
z, y, x = np.indices((frames, rows, columns))
volume = np.full((frames, rows, columns), -700, dtype='<i2')
volume[(x - 16) ** 2 + (y - 16) ** 2 <= 36] = 40
volume[(x - 16) ** 2 + (y - 16) ** 2 <= 9] = -700
for (cx, cy, cz) in markers:
    volume[max(cz - 0, 0):cz + 1, cy - 1:cy + 2, cx - 1:cx + 2] = 900


def rotation_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rotation_x(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


R = rotation_x(5) @ rotation_z(10)
t = np.array([5.0, -3.0, 2.0])
T = np.eye(4); T[:3, :3] = R; T[:3, 3] = t
study = generate_uid()
patient_name, patient_id = 'REGISTRATION^SYNTHETIC', 'SYNTHETIC-378'
series_info = {}
for label, folder, frame_uid, transform in (('fixed', 'series-a', generate_uid(), np.eye(4)), ('moving', 'series-b', generate_uid(), T)):
    series_uid = generate_uid()
    (out / folder).mkdir()
    sops = []
    for k in range(frames):
        sop = generate_uid(); sops.append(sop)
        position = transform[:3, :3] @ (origin + np.array([0, 0, k * spacing[2]])) + transform[:3, 3]
        row_dir = transform[:3, :3] @ np.array([1.0, 0, 0]); col_dir = transform[:3, :3] @ np.array([0, 1.0, 0])
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = CTImageStorage; meta.MediaStorageSOPInstanceUID = sop; meta.TransferSyntaxUID = ExplicitVRLittleEndian
        path = out / folder / f'{k + 1:03}.dcm'
        ds = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0' * 128)
        ds.SOPClassUID = CTImageStorage; ds.SOPInstanceUID = sop
        ds.StudyInstanceUID = study; ds.SeriesInstanceUID = series_uid; ds.FrameOfReferenceUID = frame_uid
        ds.PatientName = patient_name; ds.PatientID = patient_id
        ds.StudyDate = '20260913'; ds.StudyTime = '130000'; ds.Modality = 'CT'
        ds.StudyDescription = 'Synthetic registration pair'; ds.SeriesDescription = 'Registration ' + label
        ds.SeriesNumber = 1 if label == 'fixed' else 2; ds.InstanceNumber = k + 1
        ds.Rows = rows; ds.Columns = columns; ds.PixelSpacing = [spacing[1], spacing[0]]
        ds.SliceThickness = spacing[2]; ds.SpacingBetweenSlices = spacing[2]
        ds.ImageOrientationPatient = [float(v) for v in np.concatenate([row_dir, col_dir])]
        ds.ImagePositionPatient = [float(v) for v in position]
        ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = 'MONOCHROME2'
        ds.BitsAllocated = 16; ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = 1
        ds.RescaleSlope = 1; ds.RescaleIntercept = 0; ds.WindowCenter = 100; ds.WindowWidth = 1600
        ds.PixelData = volume[k].tobytes()
        ds.save_as(path, enforce_file_format=True)
    series_info[label] = {'folder': folder, 'seriesInstanceUID': series_uid, 'frameOfReferenceUID': frame_uid, 'sopInstanceUIDs': sops}

files = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*.dcm')}
manifest = {'synthetic': True, 'patientID': patient_id, 'studyInstanceUID': study, 'rows': rows, 'columns': columns, 'frames': frames,
            'spacing': spacing, 'originA': origin.tolist(), 'transformRowMajor': T.flatten().tolist(),
            'transformDescription': 'B patient frame = T · A patient frame; 10 deg about z, then 5 deg about x, then (5, -3, 2) mm',
            'markersColumnRowSlice': markers, 'series': series_info, 'sha256': files}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'output': str(out), 'series': {k: v['seriesInstanceUID'] for k, v in series_info.items()}, 'markers': markers}))
