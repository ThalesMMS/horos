#!/usr/bin/env python3
"""Compare the colours in each series thumbnail with what the file should produce.

The thumbnail is the end of the reading path, so it answers the question the
reports ask: a grey study that comes back green and purple shows it here, and so
does a colour study whose channels have been swapped or read plane-first.

`expected.json`, written by the fixture generator, holds the RGB each column
should have. `ffmpeg` decodes the thumbnails.
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

expected = json.loads((arguments.fixture / 'expected.json').read_text())
connection = sqlite3.connect(arguments.database / 'Horos Data' / 'Database.sql')
stored = dict(connection.execute('select ZNAME, ZTHUMBNAIL from ZSERIES'))

problems = []
print('%-56s %6s %6s %6s  %s' % ('series', 'red', 'green', 'blue', 'verdict'))
with tempfile.TemporaryDirectory(prefix='horos-colour-') as directory:
    for entry in expected:
        # The database strips characters the description may contain.
        blob = None
        for name, candidate in stored.items():
            if name == entry['series'] or name == entry['series'].replace(',', ''):
                blob = candidate
                break
        if blob is None:
            problems.append('%s: no series of that name in the database' % entry['series'])
            continue
        if not blob:
            problems.append('%s: no thumbnail at all' % entry['series'])
            continue

        source = Path(directory) / 'thumb.jpg'
        source.write_bytes(blob)
        raw = Path(directory) / 'thumb.rgb'
        if subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(source),
                           '-pix_fmt', 'rgb24', '-f', 'rawvideo', str(raw)],
                          capture_output=True).returncode != 0:
            problems.append('%s: the thumbnail does not decode' % entry['series'])
            continue
        data = numpy.frombuffer(raw.read_bytes(), dtype=numpy.uint8)
        side = int(round((data.size / 3) ** 0.5))
        image = data[:side * side * 3].reshape(side, side, 3).astype(float)
        columns = image.mean(axis=0)

        want = numpy.array(entry['columns'], dtype=float)
        ideal = numpy.stack([numpy.interp(numpy.linspace(0, len(want) - 1, side),
                                          numpy.arange(len(want)), want[:, channel])
                             for channel in range(3)], axis=1)
        # The edges of a rescaled thumbnail carry their neighbours' colours.
        inside = slice(4, side - 4)
        deviation = numpy.abs(columns[inside] - ideal[inside]).max(axis=0)
        colourful = float(numpy.abs(columns[inside].max(axis=1)
                                    - columns[inside].min(axis=1)).max())
        greyish = bool(numpy.abs(want.max(axis=1) - want.min(axis=1)).max() < 1)

        verdict = 'ok'
        if greyish and colourful > arguments.tolerance:
            verdict = 'COLOURED'
            problems.append('%s: a grey picture came back with up to %.0f levels between its '
                            'channels' % (entry['series'], colourful))
        elif deviation.max() > arguments.tolerance:
            verdict = 'WRONG'
            problems.append('%s: up to %.0f grey levels away from the colours the file carries'
                            % (entry['series'], deviation.max()))
        print('%-56s %6.1f %6.1f %6.1f  %s'
              % (entry['series'], deviation[0], deviation[1], deviation[2], verdict))

for problem in problems:
    print('PROBLEM: %s' % problem)
sys.exit(1 if problems else 0)
