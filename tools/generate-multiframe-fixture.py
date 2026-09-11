#!/usr/bin/env python3
"""One synthetic multiframe CT whose frames are distinguishable (#380 D).

A single enhanced-style multiframe object of `--frames` frames; frame k is a
uniform block of value 100·k plus a small square in a position that depends on
k, so the frame on screen can be identified from the pixels alone. The preview
reuses pixels from an open viewer by file path, and this fixture is how one
proves it reuses the *requested* frame.

    local-validation/venv/bin/python tools/generate-multiframe-fixture.py <empty dir>
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

MULTIFRAME_CT = '1.2.840.10008.5.1.4.1.1.2.1'  # Enhanced CT Image Storage
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--frames', type=int, default=16)
args = parser.parse_args()
if not 2 <= args.frames <= 64:
    parser.error('2-64 frames')
out = args.output.resolve()
if out == root or root in out.parents:
    raise SystemExit('output must be outside the repository')
if out.exists() and any(out.iterdir()):
    raise SystemExit('output must be empty')
out.mkdir(parents=True, exist_ok=True)

rows = columns = 64
volume = np.zeros((args.frames, rows, columns), dtype='<i2')
for k in range(args.frames):
    volume[k] = 100 * k
    x = 4 + (k % 8) * 6
    y = 4 + (k // 8) * 6
    volume[k, y:y + 5, x:x + 5] = 2000
study, series, sop = generate_uid(), generate_uid(), generate_uid()
meta = FileMetaDataset()
meta.MediaStorageSOPClassUID = MULTIFRAME_CT
meta.MediaStorageSOPInstanceUID = sop
meta.TransferSyntaxUID = ExplicitVRLittleEndian
path = out / 'multiframe.dcm'
ds = FileDataset(str(path), {}, file_meta=meta, preamble=b'\0' * 128)
ds.SOPClassUID = MULTIFRAME_CT; ds.SOPInstanceUID = sop
ds.StudyInstanceUID = study; ds.SeriesInstanceUID = series; ds.FrameOfReferenceUID = generate_uid()
ds.PatientName = 'PREVIEW^MULTIFRAME^SYNTHETIC'; ds.PatientID = 'SYNTHETIC-380-MF'
ds.StudyDate = '20260913'; ds.StudyTime = '140000'; ds.Modality = 'CT'
ds.StudyDescription = 'Synthetic multiframe preview'; ds.SeriesDescription = 'Multiframe preview'
ds.SeriesNumber = 1; ds.InstanceNumber = 1
ds.Rows = rows; ds.Columns = columns; ds.NumberOfFrames = args.frames
ds.PixelSpacing = [1, 1]; ds.SliceThickness = 1
ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]; ds.ImagePositionPatient = [-32, -32, 0]
ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = 'MONOCHROME2'
ds.BitsAllocated = 16; ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = 1
ds.RescaleSlope = 1; ds.RescaleIntercept = 0; ds.WindowCenter = 800; ds.WindowWidth = 2200
ds.PixelData = volume.tobytes()
ds.save_as(path, enforce_file_format=True)
manifest = {'synthetic': True, 'frames': args.frames, 'rows': rows, 'columns': columns,
            'sopInstanceUID': sop, 'seriesInstanceUID': series, 'studyInstanceUID': study,
            'frameMeanValue': [float(volume[k].mean()) for k in range(args.frames)],
            'sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'output': str(out), 'frames': args.frames, 'sopInstanceUID': sop}))
