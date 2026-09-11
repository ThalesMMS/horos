#!/usr/bin/env python3
"""Synthetic IVUS / ultrasound fixtures for the Volcano import crash (#107).

The 2018 report (horosproject/horos#365) never published a sample. These copies
keep the structure that matters for thumbnail initialisation — Ultrasound
Multi-frame, Sequence of Ultrasound Regions, optional IVUS Acquisition — and
none of the identifiers. A manufacturer string is optional metadata; it is not
a reason to accept or refuse the file.
"""
from pathlib import Path
import argparse
import struct
import sys


US_MULTIFRAME = '1.2.840.10008.5.1.4.1.1.3.1'
CT_IMAGE = '1.2.840.10008.5.1.4.1.1.2'
EXPLICIT_LE = '1.2.840.10008.1.2.1'
IMPLICIT_LE = '1.2.840.10008.1.2'


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


def implicit_element(group: int, element_id: int, value: bytes) -> bytes:
    return struct.pack('<HH I', group, element_id, len(value)) + value


def item(payload: bytes) -> bytes:
    return struct.pack('<HH I', 0xFFFE, 0xE000, len(payload)) + payload


def us(group, element_id, number) -> bytes:
    return element(group, element_id, 'US', struct.pack('<H', number))


def ul(group, element_id, number) -> bytes:
    return element(group, element_id, 'UL', struct.pack('<I', number))


def fd(group, element_id, number: float) -> bytes:
    return element(group, element_id, 'FD', struct.pack('<d', number))


def implicit_us(group, element_id, number) -> bytes:
    return implicit_element(group, element_id, struct.pack('<H', number))


def implicit_ul(group, element_id, number) -> bytes:
    return implicit_element(group, element_id, struct.pack('<I', number))


def implicit_fd(group, element_id, number: float) -> bytes:
    return implicit_element(group, element_id, struct.pack('<d', number))


def ultrasound_region(rows: int, columns: int, delta: float = 0.002) -> bytes:
    max_x = max(columns - 1, 0)
    max_y = max(rows - 1, 0)
    return item(b''.join([
        us(0x0018, 0x6012, 1),
        us(0x0018, 0x6014, 1),
        ul(0x0018, 0x6016, 0),
        ul(0x0018, 0x6018, 0),
        ul(0x0018, 0x601A, 0),
        ul(0x0018, 0x601C, max_x),
        ul(0x0018, 0x601E, max_y),
        us(0x0018, 0x6024, 3),
        us(0x0018, 0x6026, 3),
        fd(0x0018, 0x602C, delta),
        fd(0x0018, 0x602E, delta),
    ]))


def implicit_ultrasound_region(rows: int, columns: int, delta: float = 0.002) -> bytes:
    max_x = max(columns - 1, 0)
    max_y = max(rows - 1, 0)
    return item(b''.join([
        implicit_us(0x0018, 0x6012, 1),
        implicit_us(0x0018, 0x6014, 1),
        implicit_ul(0x0018, 0x6016, 0),
        implicit_ul(0x0018, 0x6018, 0),
        implicit_ul(0x0018, 0x601A, 0),
        implicit_ul(0x0018, 0x601C, max_x),
        implicit_ul(0x0018, 0x601E, max_y),
        implicit_us(0x0018, 0x6024, 3),
        implicit_us(0x0018, 0x6026, 3),
        implicit_fd(0x0018, 0x602C, delta),
        implicit_fd(0x0018, 0x602E, delta),
    ]))


def write_ivus_dataset(manufacturer: str, rows: int, columns: int, frames: int,
                       include_pixels: bool, photometric: str = 'MONOCHROME2',
                       ivus_acquisition='MOTOR_PULLBACK',
                       include_regions: bool = True,
                       include_palette_lut: bool = False) -> bytes:
    sop = '1.2.840.10008.5.1.4.1.1.3.1.107.1'
    study = '1.2.840.10008.5.1.4.1.1.3.1.107.2'
    series = '1.2.840.10008.5.1.4.1.1.3.1.107.3'
    parts = [
        element(0x0008, 0x0008, 'CS', lo('ORIGINAL\\PRIMARY')),
        element(0x0008, 0x0016, 'UI', ui(US_MULTIFRAME)),
        element(0x0008, 0x0018, 'UI', ui(sop)),
        element(0x0008, 0x0060, 'CS', lo('US')),
        element(0x0008, 0x0070, 'LO', lo(manufacturer)),
        element(0x0010, 0x0010, 'PN', lo('SYNTHETIC^IVUS')),
        element(0x0010, 0x0020, 'LO', lo('IVUS-107')),
        element(0x0020, 0x000D, 'UI', ui(study)),
        element(0x0020, 0x000E, 'UI', ui(series)),
    ]
    if ivus_acquisition:
        parts.append(element(0x0018, 0x3100, 'CS', lo(ivus_acquisition)))
    if include_regions:
        parts.append(element(0x0018, 0x6011, 'SQ', ultrasound_region(rows, columns)))
    parts.extend([
        us(0x0028, 0x0002, 1),
        element(0x0028, 0x0004, 'CS', lo(photometric)),
        element(0x0028, 0x0008, 'IS', lo(str(frames))),
        us(0x0028, 0x0010, rows),
        us(0x0028, 0x0011, columns),
        us(0x0028, 0x0100, 8),
        us(0x0028, 0x0101, 8),
        us(0x0028, 0x0102, 7),
        us(0x0028, 0x0103, 0),
    ])
    if include_palette_lut:
        descriptor = struct.pack('<HHH', 256, 0, 8)
        parts.append(element(0x0028, 0x1101, 'US', descriptor))
        parts.append(element(0x0028, 0x1102, 'US', descriptor))
        parts.append(element(0x0028, 0x1103, 'US', descriptor))
        lut = bytes(range(256))
        parts.append(element(0x0028, 0x1201, 'OW', lut))
        parts.append(element(0x0028, 0x1202, 'OW', lut))
        parts.append(element(0x0028, 0x1203, 'OW', lut))
    if include_pixels and rows > 0 and columns > 0:
        pixels = bytes((i * 17) % 256 for i in range(rows * columns * frames))
        parts.append(element(0x7FE0, 0x0010, 'OB', pixels))
    return b''.join(parts)


def write_implicit_ivus() -> bytes:
    rows, columns, frames = 16, 16, 2
    sop = '1.2.840.10008.5.1.4.1.1.3.1.107.11'
    body = b''.join([
        implicit_element(0x0008, 0x0008, lo('ORIGINAL\\PRIMARY')),
        implicit_element(0x0008, 0x0016, ui(US_MULTIFRAME)),
        implicit_element(0x0008, 0x0018, ui(sop)),
        implicit_element(0x0008, 0x0060, lo('US')),
        implicit_element(0x0008, 0x0070, lo('Volcano Corporation')),
        implicit_element(0x0010, 0x0010, lo('SYNTHETIC^IVUS')),
        implicit_element(0x0010, 0x0020, lo('IVUS-107-I')),
        implicit_element(0x0020, 0x000D, ui('1.2.840.10008.5.1.4.1.1.3.1.107.12')),
        implicit_element(0x0020, 0x000E, ui('1.2.840.10008.5.1.4.1.1.3.1.107.13')),
        implicit_element(0x0018, 0x3100, lo('MOTOR_PULLBACK')),
        implicit_element(0x0018, 0x6011, implicit_ultrasound_region(rows, columns)),
        implicit_us(0x0028, 0x0002, 1),
        implicit_element(0x0028, 0x0004, lo('MONOCHROME2')),
        implicit_element(0x0028, 0x0008, lo(str(frames))),
        implicit_us(0x0028, 0x0010, rows),
        implicit_us(0x0028, 0x0011, columns),
        implicit_us(0x0028, 0x0100, 8),
        implicit_us(0x0028, 0x0101, 8),
        implicit_us(0x0028, 0x0102, 7),
        implicit_us(0x0028, 0x0103, 0),
        implicit_element(0x7FE0, 0x0010, bytes((i * 13) % 256 for i in range(rows * columns * frames))),
    ])
    return body


def write_ct_control() -> bytes:
    return b''.join([
        element(0x0008, 0x0008, 'CS', lo('ORIGINAL\\PRIMARY\\AXIAL')),
        element(0x0008, 0x0016, 'UI', ui(CT_IMAGE)),
        element(0x0008, 0x0018, 'UI', ui('1.2.840.10008.5.1.4.1.1.2.107.1')),
        element(0x0008, 0x0060, 'CS', lo('CT')),
        element(0x0008, 0x0070, 'LO', lo('Synthetic Imaging')),
        element(0x0010, 0x0010, 'PN', lo('SYNTHETIC^CT')),
        element(0x0010, 0x0020, 'LO', lo('IVUS-107-CT')),
        element(0x0020, 0x000D, 'UI', ui('1.2.840.10008.5.1.4.1.1.2.107.2')),
        element(0x0020, 0x000E, 'UI', ui('1.2.840.10008.5.1.4.1.1.2.107.3')),
        us(0x0028, 0x0002, 1),
        element(0x0028, 0x0004, 'CS', lo('MONOCHROME2')),
        us(0x0028, 0x0010, 16),
        us(0x0028, 0x0011, 16),
        us(0x0028, 0x0100, 16),
        us(0x0028, 0x0101, 16),
        us(0x0028, 0x0102, 15),
        us(0x0028, 0x0103, 1),
        element(0x7FE0, 0x0010, 'OW', bytes(16 * 16 * 2)),
    ])


def wrap(dataset: bytes, sop: str, transfer: str, instance: str) -> bytes:
    meta_core = b''.join([
        element(0x0002, 0x0001, 'OB', b'\x00\x01'),
        element(0x0002, 0x0002, 'UI', ui(sop)),
        element(0x0002, 0x0003, 'UI', ui(instance)),
        element(0x0002, 0x0010, 'UI', ui(transfer)),
        element(0x0002, 0x0012, 'UI', ui('1.2.826.0.1.3680043.8.498.107')),
    ])
    meta = ul(0x0002, 0x0000, len(meta_core)) + meta_core
    return b'\x00' * 128 + b'DICM' + meta + dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    arguments = parser.parse_args()
    arguments.destination.mkdir(parents=True, exist_ok=True)

    cases = {
        'compatible.dcm': wrap(
            write_ivus_dataset('Synthetic Imaging', 32, 32, 4, True),
            US_MULTIFRAME, EXPLICIT_LE, '1.2.840.10008.5.1.4.1.1.3.1.107.1'),
        'volcano-shaped.dcm': wrap(
            write_ivus_dataset('Volcano Corporation', 32, 32, 4, True),
            US_MULTIFRAME, EXPLICIT_LE, '1.2.840.10008.5.1.4.1.1.3.1.107.1'),
        'zero-rows.dcm': wrap(
            write_ivus_dataset('Volcano Corporation', 0, 32, 4, False),
            US_MULTIFRAME, EXPLICIT_LE, '1.2.840.10008.5.1.4.1.1.3.1.107.1'),
        'empty-pixels.dcm': wrap(
            write_ivus_dataset('Synthetic Imaging', 32, 32, 4, False),
            US_MULTIFRAME, EXPLICIT_LE, '1.2.840.10008.5.1.4.1.1.3.1.107.1'),
        'palette-without-lut.dcm': wrap(
            write_ivus_dataset('Synthetic Imaging', 32, 32, 1, True,
                               photometric='PALETTE COLOR', include_palette_lut=False),
            US_MULTIFRAME, EXPLICIT_LE, '1.2.840.10008.5.1.4.1.1.3.1.107.1'),
        'implicit-le.dcm': wrap(
            write_implicit_ivus(), US_MULTIFRAME, IMPLICIT_LE,
            '1.2.840.10008.5.1.4.1.1.3.1.107.11'),
        'ct-control.dcm': wrap(
            write_ct_control(), CT_IMAGE, EXPLICIT_LE,
            '1.2.840.10008.5.1.4.1.1.2.107.1'),
    }
    for name, payload in cases.items():
        (arguments.destination / name).write_bytes(payload)
    (arguments.destination / 'not-dicom.bin').write_bytes(b'not a dicom file\n')
    print('wrote %d fixtures in %s' % (len(cases) + 1, arguments.destination))


if __name__ == '__main__':
    sys.exit(main())
