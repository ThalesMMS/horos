#!/usr/bin/env python3
"""Synthetic MRI stack whose in-plane translations are known exactly.

A bright disk on a dark field is copied onto each slice and shifted by an
integer (dx, dy). The first slice is the unshifted reference. The PoC in
MRIMotionCorrection.swift recovers those shifts by integer NCC; it does not
claim BTK slice-to-volume reconstruction.

    python3 tools/generate-mri-motion-phantom.py <empty dir> [--size 32] [--radius 7]

Writes manifest.json and one ASCII PGM per slice. Do not commit the output.
"""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('destination', type=Path)
parser.add_argument('--size', type=int, default=32)
parser.add_argument('--radius', type=float, default=7)
parser.add_argument('--spacing', type=float, default=1.25, help='mm per pixel')
arguments = parser.parse_args()

if arguments.size < 16:
    raise SystemExit('size must be at least 16 so the disk stays inside the field')
if arguments.radius < 2:
    raise SystemExit('radius must be at least 2')

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

size = arguments.size
center = ((size - 1) / 2.0, (size - 1) / 2.0)
foreground, background = 1000, 40
shifts = [[0, 0], [3, -2], [5, 1], [-4, 3], [2, 2]]


def disk(dx, dy):
    pixels = []
    cx, cy = center[0] + dx, center[1] + dy
    for y in range(size):
        row = []
        for x in range(size):
            inside = (x - cx) ** 2 + (y - cy) ** 2 <= arguments.radius ** 2
            row.append(foreground if inside else background)
        pixels.append(row)
    return pixels


def write_pgm(path, pixels):
    flat = [value for row in pixels for value in row]
    path.write_text(
        'P2\n# horos mri motion phantom\n%d %d\n%d\n%s\n' % (
            size, size, foreground,
            ' '.join(str(value) for value in flat)))


slice_names = []
for index, (dx, dy) in enumerate(shifts):
    name = 'slice-%02d.pgm' % index
    write_pgm(arguments.destination / name, disk(dx, dy))
    slice_names.append(name)

manifest = {
    'width': size,
    'height': size,
    'spacing_mm': arguments.spacing,
    'center': [center[0], center[1]],
    'radius': arguments.radius,
    'shifts_px': shifts,
    'foreground': foreground,
    'background': background,
    'slices': slice_names,
    'method': 'ncc-integer',
    'adopted': False,
    'note': 'Synthetic disk phantom for #150. Not a clinical series and not fbrain output.',
}
(arguments.destination / 'manifest.json').write_text(
    json.dumps(manifest, indent=2) + '\n')
print('wrote %d slices to %s' % (len(slice_names), arguments.destination))
