#!/usr/bin/env python3
"""Do the thumbnails in the index still show the picture, the right way up?

A thumbnail is built once, when a series is indexed, and then shown everywhere
the images themselves are not. If it is built from a misread buffer it is wrong
for the life of the database, and nothing rereads it. This decodes the thumbnail
the application stored and compares its gradients with the ones the fixture was
drawn with, which survives both the scaling and the JPEG.

    python3 tools/check-thumbnail-pixels.py <database.sql> --expect 'name=right,down'

`right` means brighter towards the right, `left` the opposite, `flat` neither.
"""
import argparse, io, sqlite3, sys
from pathlib import Path

from PIL import Image


def direction(values, tolerance):
    first, last = values[0], values[-1]
    if abs(last - first) <= tolerance:
        return 'flat'
    return 'right' if last > first else 'left'


def vertical(values, tolerance):
    first, last = values[0], values[-1]
    if abs(last - first) <= tolerance:
        return 'flat'
    return 'down' if last > first else 'up'


parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('database', type=Path, help='the Database.sql of a Horos database')
parser.add_argument('--expect', action='append', default=[],
                    help="'series name=horizontal,vertical', repeatable")
parser.add_argument('--tolerance', type=float, default=8.0,
                    help='grey levels below which a gradient counts as flat')
parser.add_argument('--list', action='store_true', help='describe every thumbnail')
options = parser.parse_args()

connection = sqlite3.connect(str(options.database))
rows = connection.execute('select ZNAME, ZTHUMBNAIL from ZSERIES').fetchall()
measured = {}
for name, blob in rows:
    if not blob:
        measured[name] = ('none', 'none', None)
        continue
    try:
        image = Image.open(io.BytesIO(bytes(blob))).convert('L')
    except Exception as exception:
        measured[name] = ('unreadable', str(exception), None)
        continue
    width, height = image.size
    columns = [sum(image.getpixel((x, y)) for y in range(height)) / height for x in range(width)]
    lines = [sum(image.getpixel((x, y)) for x in range(width)) / width for y in range(height)]
    measured[name] = (direction(columns, options.tolerance),
                      vertical(lines, options.tolerance),
                      (width, height))

if options.list:
    for name, (horizontal, vertically, size) in sorted(measured.items(), key=lambda item: str(item[0])):
        print(f'{str(name)[:46]:46s} {str(size):12s} {horizontal:10s} {vertically}')

failures = []
for expectation in options.expect:
    name, _, wanted = expectation.partition('=')
    horizontal, vertically = (wanted.split(',') + ['flat'])[:2]
    if name not in measured:
        failures.append(f'no series named {name!r} in {options.database}')
        continue
    got = measured[name]
    if got[0] != horizontal or got[1] != vertically:
        failures.append(f'{name}: thumbnail runs {got[0]}/{got[1]}, expected {horizontal}/{vertically}')

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if failures else 0)
