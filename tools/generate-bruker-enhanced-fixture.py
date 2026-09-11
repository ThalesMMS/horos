#!/usr/bin/env python3
"""Synthetic Enhanced MR fixtures for the Bruker import crash (#83).

The upstream file had patient identifiers. These copies keep the structure that
mattered - Enhanced MR, spacing only in SharedFunctionalGroupsSequence, no
window, three frames - and none of the identifiers. A manufacturer string is
optional metadata; it is not a reason to accept or refuse the file.
"""
from pathlib import Path
import argparse
import struct
import sys


ENHANCED_MR = '1.2.840.10008.5.1.4.1.1.4.1'
EXPLICIT_LE = '1.2.840.10008.1.2.1'


def pad(data: bytes) -> bytes:
    return data if len(data) % 2 == 0 else data + b'\x00'


def ui(text: str) -> bytes:
    raw = text.encode('ascii')
    return raw if len(raw) % 2 == 0 else raw + b'\x00'


def lo(text: str) -> bytes:
    return pad(text.encode('latin-1'))


def element(group: int, element_id: int, vr: str, value: bytes) -> bytes:
    tag = struct.pack('<HH', group, element_id)
    if vr in ('OB', 'OW', 'SQ', 'UN', 'UT', 'OD', 'OF', 'OL', 'UC', 'UR'):
        return tag + vr.encode('ascii') + b'\x00\x00' + struct.pack('<I', len(value)) + value
    return tag + vr.encode('ascii') + struct.pack('<H', len(value)) + value


def item(payload: bytes) -> bytes:
    return struct.pack('<HH I', 0xFFFE, 0xE000, len(payload)) + payload


def us(group, element_id, number) -> bytes:
    return element(group, element_id, 'US', struct.pack('<H', number))


def ul(group, element_id, number) -> bytes:
    return element(group, element_id, 'UL', struct.pack('<I', number))


def write_dataset(manufacturer: str, rows: int, columns: int, frames: int,
                  include_pixels: bool) -> bytes:
    sop = '1.2.840.10008.5.1.4.1.1.4.1.83.1'
    study = '1.2.840.10008.5.1.4.1.1.4.1.83.2'
    series = '1.2.840.10008.5.1.4.1.1.4.1.83.3'
    body = b''.join([
        element(0x0008, 0x0008, 'CS', lo('ORIGINAL\\PRIMARY\\NON_PARALLEL\\NONE')),
        element(0x0008, 0x0016, 'UI', ui(ENHANCED_MR)),
        element(0x0008, 0x0018, 'UI', ui(sop)),
        element(0x0008, 0x0060, 'CS', lo('MR')),
        element(0x0008, 0x0070, 'LO', lo(manufacturer)),
        element(0x0010, 0x0010, 'PN', lo('SYNTHETIC^ENHANCED')),
        element(0x0010, 0x0020, 'LO', lo('BRUKER-83')),
        element(0x0020, 0x000D, 'UI', ui(study)),
        element(0x0020, 0x000E, 'UI', ui(series)),
        us(0x0028, 0x0002, 1),
        element(0x0028, 0x0004, 'CS', lo('MONOCHROME2')),
        element(0x0028, 0x0008, 'IS', lo(str(frames))),
        us(0x0028, 0x0010, rows),
        us(0x0028, 0x0011, columns),
        us(0x0028, 0x0100, 16),
        us(0x0028, 0x0101, 16),
        us(0x0028, 0x0102, 15),
        us(0x0028, 0x0103, 1),
    ])
    measures = item(element(0x0028, 0x0030, 'DS', lo('0.234375\\0.234375')) +
                    element(0x0018, 0x0050, 'DS', lo('1')))
    shared = item(element(0x0028, 0x9110, 'SQ', measures))
    body += element(0x5200, 0x9229, 'SQ', shared)
    per_frame = b''
    for index in range(frames):
        position = item(element(0x0020, 0x0032, 'DS', lo('0\\0\\%d' % index)))
        orientation = item(element(0x0020, 0x0037, 'DS', lo('1\\0\\0\\0\\1\\0')))
        per_frame += item(element(0x0020, 0x9113, 'SQ', position) +
                          element(0x0020, 0x9116, 'SQ', orientation))
    body += element(0x5200, 0x9230, 'SQ', per_frame)
    if include_pixels and rows > 0 and columns > 0:
        pixels = bytes(rows * columns * frames * 2)
        body += element(0x7FE0, 0x0010, 'OW', pixels)
    return body


def wrap(dataset: bytes) -> bytes:
    meta_core = b''.join([
        element(0x0002, 0x0001, 'OB', b'\x00\x01'),
        element(0x0002, 0x0002, 'UI', ui(ENHANCED_MR)),
        element(0x0002, 0x0003, 'UI', ui('1.2.840.10008.5.1.4.1.1.4.1.83.1')),
        element(0x0002, 0x0010, 'UI', ui(EXPLICIT_LE)),
        element(0x0002, 0x0012, 'UI', ui('1.2.826.0.1.3680043.8.498.83')),
    ])
    meta = ul(0x0002, 0x0000, len(meta_core)) + meta_core
    return b'\x00' * 128 + b'DICM' + meta + dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    arguments = parser.parse_args()
    arguments.destination.mkdir(parents=True, exist_ok=True)

    cases = {
        'compatible.dcm': write_dataset('Synthetic Imaging', 32, 32, 3, True),
        'bruker-shaped.dcm': write_dataset('Bruker BioSpin MRI GmbH', 32, 32, 3, True),
        'zero-rows.dcm': write_dataset('Bruker BioSpin MRI GmbH', 0, 32, 3, False),
        'empty-pixels.dcm': write_dataset('Synthetic Imaging', 32, 32, 3, False),
    }
    for name, dataset in cases.items():
        (arguments.destination / name).write_bytes(wrap(dataset))
    (arguments.destination / 'not-dicom.bin').write_bytes(b'not a dicom file\n')
    print('wrote %d fixtures in %s' % (len(cases) + 1, arguments.destination))


if __name__ == '__main__':
    sys.exit(main())
