#!/usr/bin/env python3
"""DICOM byte streams that lie about their own structure.

The shapes below are the ones a parser has historically been broken by: a length
that reaches past the end of the file, a length that is nearly 2^32, an odd
length where the value representation cannot have one, a sequence that never
ends, items nested deeper than any real object goes, and a group length that
disagrees with the group. They are written as raw bytes rather than through a
DICOM library, because a library will not produce them.

None of them is a picture; the question is only whether reading them stays
inside the buffers it was given.
"""
import argparse
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

EXPLICIT_LITTLE = b'1.2.840.10008.1.2.1\x00'
IMPLICIT_LITTLE = b'1.2.840.10008.1.2\x00'
CT = b'1.2.840.10008.5.1.4.1.1.2\x00'
INSTANCE = b'1.2.826.0.1.3680043.8.498.1\x00'


def explicit(group, element, vr, value):
    """One explicit-VR little-endian element."""
    if vr in (b'OB', b'OW', b'OF', b'SQ', b'UT', b'UN'):
        return (struct.pack('<HH', group, element) + vr + b'\x00\x00'
                + struct.pack('<I', len(value)) + value)
    return struct.pack('<HH', group, element) + vr + struct.pack('<H', len(value)) + value


def explicit_lying(group, element, vr, value, declared):
    """The same, with a length of our choosing rather than the value's."""
    if vr in (b'OB', b'OW', b'OF', b'SQ', b'UT', b'UN'):
        return (struct.pack('<HH', group, element) + vr + b'\x00\x00'
                + struct.pack('<I', declared) + value)
    return struct.pack('<HH', group, element) + vr + struct.pack('<H', declared) + value


def implicit(group, element, value, declared=None):
    length = len(value) if declared is None else declared
    return struct.pack('<HHI', group, element, length) + value


def meta(transfer_syntax=EXPLICIT_LITTLE):
    group = b''
    group += explicit(0x0002, 0x0002, b'UI', CT)
    group += explicit(0x0002, 0x0003, b'UI', INSTANCE)
    group += explicit(0x0002, 0x0010, b'UI', transfer_syntax)
    group += explicit(0x0002, 0x0012, b'UI', b'1.2.826.0.1.3680043.8.498.9\x00')
    length = explicit(0x0002, 0x0000, b'UL', struct.pack('<I', len(group)))
    return b'\x00' * 128 + b'DICM' + length + group


def write(name, description, body, transfer_syntax=EXPLICIT_LITTLE):
    path = arguments.destination / ('%s.dcm' % name)
    path.write_bytes(meta(transfer_syntax) + body)
    print('%-22s %-56s %d bytes' % (name, description, path.stat().st_size))


ordinary = (explicit(0x0008, 0x0016, b'UI', CT)
            + explicit(0x0008, 0x0018, b'UI', INSTANCE)
            + explicit(0x0028, 0x0010, b'US', struct.pack('<H', 4))
            + explicit(0x0028, 0x0011, b'US', struct.pack('<H', 4)))

write('ordinary', 'a small well-formed object, as a control',
      ordinary + explicit(0x7FE0, 0x0010, b'OW', b'\x01\x02' * 16))

write('length-past-end', 'a value length reaching far past the end of the file',
      ordinary + explicit_lying(0x7FE0, 0x0010, b'OW', b'\x01\x02' * 4, 0x00100000))

write('length-almost-4g', 'a value length of 0xFFFFFFF0',
      ordinary + explicit_lying(0x7FE0, 0x0010, b'OW', b'\x01\x02' * 4, 0xFFFFFFF0))

write('odd-length', 'an odd length on a value representation that cannot have one',
      ordinary + explicit_lying(0x0008, 0x0020, b'DA', b'20260101', 7))

# A sequence opened with an undefined length and never closed.
write('sequence-never-ends', 'a sequence of undefined length with no delimiter',
      ordinary + struct.pack('<HH', 0x0008, 0x1140) + b'SQ\x00\x00' + struct.pack('<I', 0xFFFFFFFF)
      + struct.pack('<HHI', 0xFFFE, 0xE000, 0xFFFFFFFF)
      + explicit(0x0008, 0x1155, b'UI', INSTANCE))

# Items nested far deeper than any real object.
nested = b''
for _ in range(2000):
    nested = (struct.pack('<HH', 0x0008, 0x1140) + b'SQ\x00\x00' + struct.pack('<I', 0xFFFFFFFF)
              + struct.pack('<HHI', 0xFFFE, 0xE000, 0xFFFFFFFF)
              + nested
              + struct.pack('<HHI', 0xFFFE, 0xE00D, 0)
              + struct.pack('<HHI', 0xFFFE, 0xE0DD, 0))
write('nested-2000-deep', 'two thousand nested sequences', ordinary + nested)

write('item-past-end', 'a sequence item whose length points past the end',
      ordinary + struct.pack('<HH', 0x0008, 0x1140) + b'SQ\x00\x00' + struct.pack('<I', 24)
      + struct.pack('<HHI', 0xFFFE, 0xE000, 0x00FFFFFF)
      + explicit(0x0008, 0x1155, b'UI', INSTANCE))

write('group-length-lies', 'a group length twice the size of its group',
      explicit(0x0008, 0x0000, b'UL', struct.pack('<I', 4096)) + ordinary)

write('implicit-undefined', 'an implicit-VR element of undefined length that is not a sequence',
      implicit(0x0008, 0x0016, CT) + implicit(0x7FE0, 0x0010, b'\x01\x02' * 4, 0xFFFFFFFF),
      transfer_syntax=IMPLICIT_LITTLE)

write('unknown-vr-huge', 'an element of unknown value representation claiming 1 GB',
      ordinary + explicit_lying(0x0009, 0x0001, b'UN', b'\x00' * 8, 0x40000000))

write('truncated-mid-element', 'a file that stops in the middle of a value',
      (ordinary + struct.pack('<HH', 0x7FE0, 0x0010) + b'OW\x00\x00'
       + struct.pack('<I', 4096) + b'\x01\x02\x03'))

write('meta-only', 'a file meta group and nothing after it', b'')

write('not-dicom-at-all', 'a file whose magic is right and whose contents are not',
      b'\xff' * 512)

print()
print('%d files in %s' % (len(list(arguments.destination.iterdir())), arguments.destination))
