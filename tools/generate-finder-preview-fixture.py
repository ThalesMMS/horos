#!/usr/bin/env python3
"""Write small synthetic DICOM files for Finder preview acceptance.

The supported files are Explicit and Implicit VR Little Endian 32x32
MONOCHROME2 images with a left/right step that a pixel test can measure.
The unsupported file declares JPEG-LS lossless and does not need a real
JPEG-LS payload: the extension must refuse the transfer syntax before it
treats the bytes as pixels. Nothing here is a clinical image.
"""
import argparse
import hashlib
import struct
from pathlib import Path

IMPLICIT = '1.2.840.10008.1.2'
EXPLICIT = '1.2.840.10008.1.2.1'
JPEG_LS = '1.2.840.10008.1.2.4.80'
SC = '1.2.840.10008.5.1.4.1.1.7'
IMPLEMENTATION = '2.25.141'


def uid(name):
    digest = hashlib.sha256(('horos-finder-preview-' + name).encode()).hexdigest()
    return '2.25.' + str(int(digest[:32], 16))


def even(blob):
    return blob if len(blob) % 2 == 0 else blob + b'\x00'


def explicit(group, element, vr, value):
    tag = struct.pack('<HH', group, element)
    if vr in ('OB', 'OW', 'OF', 'SQ', 'UT', 'UN', 'OD', 'OL', 'UC', 'UR'):
        return tag + vr.encode('ascii') + b'\x00\x00' + struct.pack('<I', len(value)) + value
    return tag + vr.encode('ascii') + struct.pack('<H', len(value)) + value


def implicit(group, element, value):
    return struct.pack('<HH', group, element) + struct.pack('<I', len(value)) + value


def ui(text):
    return even(text.encode('ascii'))


def step_pixels(rows=32, columns=32, left=40, right=200):
    return bytes(left if x < columns // 2 else right
                 for y in range(rows) for x in range(columns))


def file_meta(sop, instance, transfer):
    payload = b''.join([
        explicit(0x0002, 0x0001, 'OB', b'\x00\x01'),
        explicit(0x0002, 0x0002, 'UI', ui(sop)),
        explicit(0x0002, 0x0003, 'UI', ui(instance)),
        explicit(0x0002, 0x0010, 'UI', ui(transfer)),
        explicit(0x0002, 0x0012, 'UI', ui(IMPLEMENTATION)),
    ])
    return explicit(0x0002, 0x0000, 'UL', struct.pack('<I', len(payload))) + payload


def image_elements(instance, rows, columns, pixels, syntax):
    def put(group, element, vr, value):
        return explicit(group, element, vr, value) if syntax != IMPLICIT else implicit(group, element, value)

    return b''.join([
        put(0x0008, 0x0016, 'UI', ui(SC)),
        put(0x0008, 0x0018, 'UI', ui(instance)),
        put(0x0008, 0x0060, 'CS', even(b'OT')),
        put(0x0010, 0x0010, 'PN', even(b'QA^FinderPreview')),
        put(0x0010, 0x0020, 'LO', even(b'LOCAL-FINDER-PREVIEW')),
        put(0x0020, 0x000D, 'UI', ui(uid('study'))),
        put(0x0020, 0x000E, 'UI', ui(uid('series-' + syntax))),
        put(0x0028, 0x0002, 'US', struct.pack('<H', 1)),
        put(0x0028, 0x0004, 'CS', even(b'MONOCHROME2')),
        put(0x0028, 0x0010, 'US', struct.pack('<H', rows)),
        put(0x0028, 0x0011, 'US', struct.pack('<H', columns)),
        put(0x0028, 0x0100, 'US', struct.pack('<H', 8)),
        put(0x0028, 0x0101, 'US', struct.pack('<H', 8)),
        put(0x0028, 0x0102, 'US', struct.pack('<H', 7)),
        put(0x0028, 0x0103, 'US', struct.pack('<H', 0)),
        put(0x7FE0, 0x0010, 'OB', even(pixels)),
    ])


def write_dicom(path, transfer, pixels=None):
    instance = uid(path.name)
    body = file_meta(SC, instance, transfer)
    body += image_elements(instance, 32, 32, pixels if pixels is not None else step_pixels(), transfer)
    path.write_bytes(b'\x00' * 128 + b'DICM' + body)


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Use an empty output directory')
    write_dicom(output / 'supported-explicit.dcm', EXPLICIT)
    write_dicom(output / 'supported-implicit.dcm', IMPLICIT)
    # Encapsulated-looking payload so a naive reader cannot treat it as 8-bit.
    bogus = struct.pack('<HH I', 0xFFFE, 0xE000, 0) + struct.pack('<HH I', 0xFFFE, 0xE000, 4) + b'NOPE'
    write_dicom(output / 'unsupported-jpegls.dcm', JPEG_LS, bogus)
    (output / 'not-dicom.dcm').write_bytes(b'this is not a dicom file')
    (output / 'README.txt').write_text(
        'Synthetic Finder preview fixtures. Not clinical images.\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    generate(parser.parse_args().output)
