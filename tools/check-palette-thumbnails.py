#!/usr/bin/env python3
"""Do the colours in the thumbnail match the lookup table the file carries?

The fixture's palette is chosen so the three channels cannot be confused: red
rises with the index, green falls, blue is a constant. The picture is an index
ramp, so the thumbnail should be a red-to-green gradient over a flat blue.

This reads the thumbnail the application wrote for each series, decodes it with
`ffmpeg`, and compares each channel's column means against what the file's own
table says they should be.
"""
import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path, help='the directory holding expected.json')
parser.add_argument('database', type=Path, help='the database location Horos was given')
parser.add_argument('--tolerance', type=float, default=20.0,
                    help='grey levels of slack, for JPEG and the thumbnail rescale')
arguments = parser.parse_args()

ffmpeg = shutil.which('ffmpeg')
if ffmpeg is None:
    raise SystemExit('ffmpeg is needed to decode the thumbnails and is not here')

expected = {entry['series']: entry
            for entry in json.loads((arguments.fixture / 'expected.json').read_text())}
connection = sqlite3.connect(arguments.database / 'Horos Data' / 'Database.sql')

problems = []
print('%-52s %7s %7s %7s' % ('series', 'red', 'green', 'blue'))
with tempfile.TemporaryDirectory(prefix='horos-palette-') as directory:
    for name, blob in connection.execute('select ZNAME, ZTHUMBNAIL from ZSERIES order by ZID'):
        want = None
        for description, entry in expected.items():
            # The database strips characters the fixture put in the description.
            if description.replace(',', '') == name or description == name:
                want = entry
                break
        if not blob:
            print('%-52s %7s %7s %7s' % (name, '-', '-', '-'))
            problems.append('%s: no thumbnail at all' % name)
            continue

        source = Path(directory) / 'thumb.jpg'
        source.write_bytes(blob)
        raw = Path(directory) / 'thumb.rgb'
        if subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(source),
                           '-pix_fmt', 'rgb24', '-f', 'rawvideo', str(raw)],
                          capture_output=True).returncode != 0:
            problems.append('%s: the thumbnail does not decode' % name)
            continue
        data = numpy.frombuffer(raw.read_bytes(), dtype=numpy.uint8)
        side = int(round((data.size / 3) ** 0.5))
        image = data[:side * side * 3].reshape(side, side, 3).astype(float)
        columns = image.mean(axis=0)

        if want is None:
            print('%-52s %7s %7s %7s   (not in the fixture)'
                  % (name, '%.0f' % columns[:, 0].mean(), '%.0f' % columns[:, 1].mean(),
                     '%.0f' % columns[:, 2].mean()))
            continue

        # What the table says the picture should look like, at the thumbnail's width.
        want_index = numpy.interp(numpy.linspace(0, side - 1, side),
                                  numpy.linspace(0, side - 1, len(want['columns'])),
                                  want['columns'])
        entry = numpy.clip(numpy.round(want_index - want['first']).astype(int),
                           0, want['entries'] - 1)
        ideal = numpy.stack([numpy.array(want[channel])[entry]
                             for channel in ('red', 'green', 'blue')], axis=1).astype(float)

        # The edges of a rescaled thumbnail carry the neighbouring rows' colours.
        inside = slice(4, side - 4)
        deviation = numpy.abs(columns[inside] - ideal[inside]).max(axis=0)
        print('%-52s %7.1f %7.1f %7.1f' % (name, deviation[0], deviation[1], deviation[2]))
        for channel, off in zip(('red', 'green', 'blue'), deviation):
            if off > arguments.tolerance:
                problems.append('%s: %s is up to %.0f grey levels away from the table the file '
                                'carries' % (name, channel, off))

for problem in problems:
    print('PROBLEM: %s' % problem)
sys.exit(1 if problems else 0)
