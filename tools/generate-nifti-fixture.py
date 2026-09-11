#!/usr/bin/env python3
"""A NIfTI-1 volume whose geometry and values are known exactly.

The header is written field by field rather than through a library, so the
fixture is the specification and not a second implementation's opinion of it -
and so this generator needs nothing but numpy. Every number below is chosen to
make a mistake visible:

    in-plane spacing 0.5 mm, slice spacing 3.0 mm

        different on purpose. Code that advances a slice position by the in-plane
        spacing instead of the slice spacing gets the stack six times too short,
        and no fixture with cubic voxels would show it.

    intensity            each slice is filled with 100 * (index + 1)

        so a slice read from the wrong offset, or bytes swapped, is a wrong
        number rather than a wrong picture.

    orientation          identity affine, LAS/axial by qform, qform_code 1

        the plainest case there is; anything that comes out rotated came out
        rotated from nothing.

    python3 tools/generate-nifti-fixture.py <empty dir> [--slices 8] [--size 16]
"""
import argparse
import struct
from pathlib import Path

import numpy

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--slices', type=int, default=8)
parser.add_argument('--size', type=int, default=16)
parser.add_argument('--in-plane', type=float, default=0.5, dest='in_plane', help='mm')
parser.add_argument('--slice-spacing', type=float, default=3.0, dest='slice_spacing', help='mm')
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size, slices = arguments.size, arguments.slices
DT_SIGNED_SHORT, BITPIX = 4, 16
NIFTI_UNITS_MM, NIFTI_UNITS_SEC = 2, 8

header = bytearray(348)


def put(offset, form, *values):
    struct.pack_into(form, header, offset, *values)


put(0, '<i', 348)                                   # sizeof_hdr
put(38, '<c', b'r')                                 # regular
put(40, '<8h', 3, size, size, slices, 1, 1, 1, 1)   # dim: three dimensions
put(70, '<h', DT_SIGNED_SHORT)
put(72, '<h', BITPIX)
# pixdim[0] is qfac, +1 for a right-handed frame; then x, y, z spacing in mm.
put(76, '<8f', 1.0, arguments.in_plane, arguments.in_plane, arguments.slice_spacing, 0, 0, 0, 0)
put(108, '<f', 352.0)                               # vox_offset, single-file form
put(112, '<f', 1.0)                                 # scl_slope: values are as written
put(116, '<f', 0.0)                                 # scl_inter
put(123, '<B', NIFTI_UNITS_MM | NIFTI_UNITS_SEC)    # xyzt_units
put(148, '<80s', b'horos fixture: 0.5 mm in plane, 3.0 mm between slices')
put(252, '<h', 1)                                   # qform_code: scanner anatomical
put(254, '<h', 1)                                   # sform_code, filled to agree
put(256, '<3f', 0.0, 0.0, 0.0)                      # quatern b, c, d: no rotation
put(268, '<3f', 0.0, 0.0, 0.0)                      # qoffset x, y, z
put(280, '<4f', arguments.in_plane, 0.0, 0.0, 0.0)  # srow_x
put(296, '<4f', 0.0, arguments.in_plane, 0.0, 0.0)  # srow_y
put(312, '<4f', 0.0, 0.0, arguments.slice_spacing, 0.0)  # srow_z
put(344, '<4s', b'n+1\x00')                         # magic: header and data in one file

volume = numpy.zeros((slices, size, size), dtype='<i2')
for index in range(slices):
    volume[index, :, :] = 100 * (index + 1)

path = arguments.destination / 'geometry.nii'
with open(path, 'wb') as out:
    out.write(bytes(header))
    out.write(b'\0' * 4)                            # 348 -> vox_offset 352
    out.write(volume.tobytes())

print('%-16s %d x %d x %d' % ('volume', size, size, slices))
print('%-16s %.2f mm in plane, %.2f mm between slices' % ('spacing', arguments.in_plane,
                                                          arguments.slice_spacing))
print('%-16s slice n holds %d' % ('values', 100))
print('%-16s %s (%d bytes)' % ('file', path, path.stat().st_size))
