#!/usr/bin/env python3
"""Shipped dciodvfy is arm64-only and validates a synthetic DICOM without Rosetta."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
archive = root / 'Binaries/dciodvfy.zip'
if not archive.is_file():
    print('FAIL: Binaries/dciodvfy.zip is missing', file=sys.stderr)
    sys.exit(1)


def element(group, number, vr, payload):
    if vr == b'OB':
        if len(payload) % 2:
            payload += b'\x00'
        return struct.pack('<HH2sHI', group, number, vr, 0, len(payload)) + payload
    if len(payload) % 2:
        payload += b'\x00' if vr == b'UI' else b' '
    return struct.pack('<HH2sH', group, number, vr, len(payload)) + payload


CLASS_UID = b'1.2.840.10008.5.1.4.1.1.7'
INSTANCE_UID = b'1.2.826.0.1.3680043.8.498.37001'
EXPLICIT_LITTLE = b'1.2.840.10008.1.2.1'
meta = (element(0x0002, 0x0001, b'OB', b'\x00\x01')
        + element(0x0002, 0x0002, b'UI', CLASS_UID)
        + element(0x0002, 0x0003, b'UI', INSTANCE_UID)
        + element(0x0002, 0x0010, b'UI', EXPLICIT_LITTLE)
        + element(0x0002, 0x0012, b'UI', b'1.2.826.0.1.3680043.8.498.1'))
meta = element(0x0002, 0x0000, b'UL', struct.pack('<I', len(meta))) + meta
dataset = (element(0x0008, 0x0016, b'UI', CLASS_UID)
           + element(0x0008, 0x0018, b'UI', INSTANCE_UID)
           + element(0x0008, 0x0020, b'DA', b'20260911')
           + element(0x0008, 0x0030, b'TM', b'220000')
           + element(0x0008, 0x0060, b'CS', b'OT')
           + element(0x0010, 0x0010, b'PN', b'QA^DCIODVFY')
           + element(0x0010, 0x0020, b'LO', b'LOCAL-DCIODVFY')
           + element(0x0020, 0x000D, b'UI', b'1.2.826.0.1.3680043.8.498.37002')
           + element(0x0020, 0x000E, b'UI', b'1.2.826.0.1.3680043.8.498.37003')
           + element(0x0020, 0x0010, b'SH', b'DCIOD')
           + element(0x0020, 0x0011, b'IS', b'1')
           + element(0x0020, 0x0013, b'IS', b'1'))
fixture = b'\x00' * 128 + b'DICM' + meta + dataset

with tempfile.TemporaryDirectory(prefix='horos-dciodvfy-') as directory:
    folder = Path(directory)
    with zipfile.ZipFile(archive) as zipped:
        zipped.extract('dciodvfy', folder)
    helper = folder / 'dciodvfy'
    helper.chmod(0o755)
    archs = subprocess.run(['lipo', '-archs', str(helper)], capture_output=True, text=True, check=True)
    slices = archs.stdout.split()
    if slices != ['arm64']:
        print('FAIL: shipped dciodvfy must be arm64-only, got', slices, file=sys.stderr)
        sys.exit(1)
    dicom = folder / 'qa.dcm'
    dicom.write_bytes(fixture)
    native = subprocess.run([str(helper), str(dicom)], capture_output=True, text=True)
    text = native.stdout + native.stderr
    if 'SCImage' not in text:
        print('FAIL: native dciodvfy did not identify Secondary Capture:\n', text, file=sys.stderr)
        sys.exit(1)
    if 'Missing attribute' not in text:
        print('FAIL: native dciodvfy did not report IOD gaps:\n', text, file=sys.stderr)
        sys.exit(1)
    rosetta = subprocess.run(['arch', '-x86_64', str(helper), str(dicom)], capture_output=True, text=True)
    if rosetta.returncode == 0:
        print('FAIL: dciodvfy must not be an Intel/universal binary', file=sys.stderr)
        sys.exit(1)
    print('PASS: dciodvfy is arm64-only, identifies SCImage, and reports IOD gaps without Rosetta')
