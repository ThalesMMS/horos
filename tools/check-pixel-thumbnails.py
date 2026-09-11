#!/usr/bin/env python3
"""What the database's own thumbnail says about the pixels behind it.

Horos builds a series thumbnail from the decoded image, so the thumbnail is the
end of the reading path rather than a copy of the file. A picture that was read
correctly keeps its shape; one whose words were reinterpreted as something else
comes out flat, and one read in halves comes out banded.

The fixture's picture is a left-to-right ramp windowed by the file's own
WindowCenter and WindowWidth, which cover exactly the range that variant holds.
So a thumbnail that runs from black to white along a straight line says more than
"something was displayed": it says the decoded values filled the range the file
declared. Values that arrived halved, truncated to sixteen bits, or reinterpreted
would no longer match their own window, and the ramp would clip or flatten.

This reports, per series, how many distinct grey levels the thumbnail holds, its
first and last column, and how far the column means stray from a straight line.
`ffmpeg` does the decoding.
"""
import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('database', type=Path, help='the database location Horos was given')
parser.add_argument('--expect-ramp', action='append', default=[],
                    help='series description that must hold a left-to-right ramp; repeatable')
arguments = parser.parse_args()

ffmpeg = shutil.which('ffmpeg')
if ffmpeg is None:
    raise SystemExit('ffmpeg is needed to decode the thumbnails and is not here')

connection = sqlite3.connect(arguments.database / 'Horos Data' / 'Database.sql')
rows = connection.execute(
    'select ZNAME, ZTHUMBNAIL from ZSERIES order by ZID').fetchall()

problems = []
print('%-46s %6s %6s %6s %7s %s'
      % ('series', 'levels', 'first', 'last', 'straight', 'thumbnail'))
seen = {}
with tempfile.TemporaryDirectory(prefix='horos-thumb-') as directory:
    for name, blob in rows:
        if not blob:
            print('%-46s %6s %6s %6s %7s %s' % (name, '-', '-', '-', '-', 'none stored'))
            seen[name] = None
            continue
        source = Path(directory) / 'thumb.jpg'
        source.write_bytes(blob)
        raw = Path(directory) / 'thumb.gray'
        probe = subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(source),
                                '-pix_fmt', 'gray', '-f', 'rawvideo', str(raw)],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            problems.append('%s: the thumbnail does not decode: %s' % (name, probe.stderr[-200:]))
            continue
        size = subprocess.run([ffmpeg, '-i', str(source)], capture_output=True, text=True).stderr
        dimensions = [part for part in size.split() if 'x' in part and part[0].isdigit()]
        width = height = None
        for candidate in dimensions:
            piece = candidate.strip(',')
            if piece.count('x') == 1 and all(p.isdigit() for p in piece.split('x')):
                width, height = (int(p) for p in piece.split('x'))
                break
        data = numpy.frombuffer(raw.read_bytes(), dtype=numpy.uint8)
        if width and height and data.size >= width * height:
            image = data[:width * height].reshape(height, width)
        else:
            problems.append('%s: cannot tell the thumbnail size from %r' % (name, dimensions))
            continue
        levels = len(numpy.unique(image))
        columns = image.mean(axis=0).astype(float)
        # Allow for JPEG ringing: the trend has to rise, not every step.
        monotone = bool(numpy.all(numpy.diff(columns[::4]) > -2.0)
                        and columns[-1] - columns[0] > 32)
        straight = float(numpy.abs(
            columns - numpy.linspace(columns[0], columns[-1], len(columns))).max())
        seen[name] = (levels, monotone, straight)
        print('%-46s %6d %6.1f %6.1f %7.1f %d bytes, %dx%d'
              % (name, levels, columns[0], columns[-1], straight, len(blob), width, height))

for wanted in arguments.expect_ramp:
    match = [key for key in seen if wanted in key]
    if not match:
        problems.append('no series called %r' % wanted)
        continue
    result = seen[match[0]]
    if result is None:
        problems.append('%s: no thumbnail at all, so nothing was displayed' % match[0])
    elif result[0] <= 2:
        problems.append('%s: the thumbnail holds %d grey level(s) - the picture is flat, so the '
                        'values did not survive' % (match[0], result[0]))
    elif not result[1]:
        problems.append('%s: the thumbnail is not a left-to-right ramp, so the values were '
                        'not read as they were written' % match[0])
    elif result[2] > 12.0:
        problems.append('%s: the ramp strays %.1f grey levels from a straight line, so the '
                        'values do not fill the window the file declares' % (match[0], result[2]))

for problem in problems:
    print('PROBLEM: %s' % problem)
sys.exit(1 if problems else 0)
