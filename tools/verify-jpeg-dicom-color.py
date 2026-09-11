#!/usr/bin/env python3
"""Compare a native JPEG-to-DICOM conversion with independent RGB decoders.

Requires pydicom, NumPy and FFmpeg. Intended for the controlled RGB chart fixture.
"""
import argparse
import shutil
import subprocess
from pathlib import Path
import pydicom


def verify(jpeg, dicom):
    ds = pydicom.dcmread(dicom)
    assert ds.PhotometricInterpretation == 'RGB'
    assert ds.SamplesPerPixel == 3 and ds.PlanarConfiguration == 0
    assert ds.BitsAllocated == ds.BitsStored == 8 and ds.HighBit == 7
    assert ds.PixelRepresentation == 0
    assert str(ds.file_meta.TransferSyntaxUID) == '1.2.840.10008.1.2.1'
    pixels = ds.pixel_array  # pydicom's independent DICOM decoder
    assert pixels.shape == (128, 192, 3), pixels.shape
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg must be on PATH')
    reference = subprocess.check_output([ffmpeg, '-v', 'error', '-i', str(jpeg),
        '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'])
    assert pixels.tobytes() == reference, 'Decoded RGB differs from source JPEG'
    print('PASS: DICOM metadata and 192x128 RGB pixels match independent JPEG decode exactly')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jpeg', type=Path)
    parser.add_argument('dicom', type=Path)
    args = parser.parse_args()
    verify(args.jpeg, args.dicom)
