#!/usr/bin/env python3
"""Generate a synthetic lossless CT series for native loading measurements.

Requires numpy, pydicom and imagecodecs. Preserve the output manifest and import
only the dicom subfolder into an isolated Horos database. No clinical data.
"""
import argparse
import hashlib
import json
from pathlib import Path

import imagecodecs
import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import CTImageStorage, JPEG2000Lossless, generate_uid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--slices', type=int, default=512)
parser.add_argument('--size', type=int, default=512)
args = parser.parse_args()
if not 1 <= args.slices <= 2048 or not 64 <= args.size <= 1024:
    parser.error('Use 1..2048 slices and 64..1024 pixels per dimension')
if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
    parser.error('Use an empty output directory')
folder = args.output/'dicom'
folder.mkdir(parents=True)
study, series, frame = generate_uid(), generate_uid(), generate_uid()
manifest = dict(patient='SYNTHETIC-OPJ-PERF', study=study, series=series,
    slices=args.slices, size=args.size, transferSyntax=str(JPEG2000Lossless), instances=[])
y, x = np.mgrid[:args.size, :args.size]
for index in range(args.slices):
    pixels = ((x*17 + y*31 + ((x//32) ^ (y//32))*1024 + index*113) & 65535).astype('<u2')
    encoded = imagecodecs.jpeg2k_encode(pixels, level=0, reversible=True,
        codecformat='J2K', bitspersample=16)
    if not np.array_equal(imagecodecs.jpeg2k_decode(encoded), pixels):
        raise RuntimeError(f'Encoder roundtrip changed slice {index}')
    ds = Dataset(); ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = JPEG2000Lossless
    ds.SOPClassUID = CTImageStorage; ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = study; ds.SeriesInstanceUID = series
    ds.FrameOfReferenceUID = frame
    ds.PatientID = manifest['patient']; ds.PatientName = 'SYNTHETIC^OpenJPEG Performance'
    ds.StudyDate = '20260914'; ds.StudyTime = '120000'; ds.StudyID = 'OPJPERF'
    ds.StudyDescription = 'Synthetic JPEG2000 performance'
    ds.SeriesDescription = f'Synthetic J2K {args.slices} x {args.size} x {args.size}'
    ds.SeriesNumber = 1; ds.InstanceNumber = index + 1; ds.Modality = 'CT'
    ds.Manufacturer = 'Synthetic generator'; ds.ImageType = ['ORIGINAL', 'PRIMARY', 'AXIAL']
    ds.Rows = ds.Columns = args.size; ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 16; ds.HighBit = 15; ds.PixelRepresentation = 0
    ds.PixelSpacing = [1, 1]; ds.SliceThickness = 1
    ds.ImagePositionPatient = [0, 0, index]; ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.RescaleSlope = 1; ds.RescaleIntercept = 0
    ds.WindowCenter = 32768; ds.WindowWidth = 65536
    ds.PixelData = encapsulate([encoded]); ds['PixelData'].is_undefined_length = True
    path = folder/f'{index+1:04d}.dcm'
    ds.save_as(path, enforce_file_format=True)
    manifest['instances'].append(dict(file=str(path.relative_to(args.output)),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        pixelSHA256=hashlib.sha256(pixels.tobytes()).hexdigest()))
(args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(f'Generated and verified {args.slices} synthetic {args.size}x{args.size} slices')
