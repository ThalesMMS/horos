#!/usr/bin/env python3
"""Generate JPEG 2000 lossless multiframe instances, the shape tomosynthesis has.

Two copies of the same pixels under different identifiers: one to import from
disk, one to serve over WADO, so what arrives by each route can be compared
frame by frame. Lossless, so any difference in the pixels is a defect and not a
codec.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from openjpeg import encode
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import JPEG2000Lossless, generate_uid

BREAST_TOMOSYNTHESIS = '1.2.840.10008.5.1.4.1.1.13.1.3'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path)
parser.add_argument('--frames', type=int, default=8)
parser.add_argument('--size', type=int, default=64, help='rows and columns')
args = parser.parse_args()
if not 1 <= args.frames <= 64 or not 16 <= args.size <= 512:
    parser.error('Keep the fixture small')
args.destination.mkdir(parents=True, exist_ok=True)
if any(args.destination.iterdir()):
    parser.error('Use an empty destination')

# One pattern per frame, distinct enough that a frame served in the wrong order
# or dropped is visible.
rows = columns = args.size
frames = []
for frame in range(args.frames):
    y, x = np.mgrid[0:rows, 0:columns]
    pattern = ((x * 7 + y * 13 + frame * 211) % 4096).astype('<u2')
    pattern[frame % rows, :] = 4095          # a moving bright line
    frames.append(np.ascontiguousarray(pattern))

encoded = [encode(frame, bits_stored=12, photometric_interpretation=2, use_mct=False,
                  codec_format=0) for frame in frames]
manifest = {'frames': args.frames, 'rows': rows, 'columns': columns,
            'frame_sha256': [hashlib.sha256(frame.tobytes()).hexdigest() for frame in frames],
            'instances': {}}


def write(name, description):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = JPEG2000Lossless
    ds.SOPClassUID = BREAST_TOMOSYNTHESIS
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientName = 'QA^Tomo'
    ds.PatientID = 'LOCAL-TOMO'
    ds.StudyDate = '20260909'
    ds.StudyTime = '120000'
    ds.StudyID = 'TOMO'
    ds.StudyDescription = description
    ds.SeriesDescription = description
    ds.SeriesNumber = 1
    ds.InstanceNumber = 1
    ds.Modality = 'MG'
    ds.Rows = rows
    ds.Columns = columns
    ds.NumberOfFrames = args.frames
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = 16
    ds.BitsStored = 12
    ds.HighBit = 11
    ds.PixelRepresentation = 0
    ds.PixelSpacing = [1, 1]
    ds.PixelData = encapsulate(encoded)
    ds['PixelData'].is_undefined_length = True
    path = args.destination / name
    ds.save_as(path, enforce_file_format=True)
    manifest['instances'][name] = {'sop_instance': str(ds.SOPInstanceUID),
                                   'study': str(ds.StudyInstanceUID),
                                   'series': str(ds.SeriesInstanceUID)}
    return ds


write('local.dcm', 'Tomosynthesis imported from disk')
write('wado.dcm', 'Tomosynthesis retrieved over WADO')
(args.destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('frames %d of %dx%d, JPEG 2000 lossless' % (args.frames, rows, columns))
for name, record in manifest['instances'].items():
    print('  %-10s %s' % (name, record['sop_instance']))
