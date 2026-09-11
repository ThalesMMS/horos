#!/usr/bin/env python3
"""Compare what a C-MOVE fixture said it sent with what the database ended up with.

A study can look complete in a study list and still be short. A multiframe
instance is one file and many rows, so a lost instance shows up as a smaller
frame count and nothing else, and a file that arrived truncated shows up as
nothing at all until someone tries to display it.

This reads the fixture's own record of every instance it sent, every file the
database stores, and the pixels in those files, and says whether the three agree:
the SOP Instance UIDs that were sent are the ones on disk, each file decodes, and
each frame of each file is there and is the size the header claims.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

import pydicom

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence', type=Path, help='the fixture directory holding cmove-sent.json')
parser.add_argument('database', type=Path, help='the database location Horos was given')
arguments = parser.parse_args()

record = json.loads((arguments.evidence / 'cmove-sent.json').read_text())
sent = {}
for move in record['moves']:
    for instance in move['sent']:
        sent[instance['sopInstance']] = instance['frames']
withheld = {instance['sopInstance']: instance['frames'] for move in record['moves']
            for instance in move.get('refusedInstances', [])}

base = arguments.database / 'Horos Data'
connection = sqlite3.connect(base / 'Database.sql')
rows = connection.execute('select count(*) from ZIMAGE').fetchone()[0]

problems = []
stored = {}
for path in sorted((base / 'DATABASE.noindex').rglob('*')):
    if not path.is_file() or path.name.startswith('.'):
        continue
    try:
        dataset = pydicom.dcmread(str(path))
    except Exception as error:                                  # noqa: BLE001
        problems.append('%s is not readable: %s' % (path.name, error))
        continue
    uid = str(dataset.SOPInstanceUID)
    frames = int(getattr(dataset, 'NumberOfFrames', 1))
    stored[uid] = frames
    try:
        pixels = dataset.pixel_array
    except Exception as error:                                  # noqa: BLE001
        problems.append('%s holds no readable pixels: %s' % (uid, error))
        continue
    # Every frame has to be there, and be the size the header promised.
    expected = (int(dataset.Rows), int(dataset.Columns))
    if frames > 1:
        if pixels.shape[0] != frames:
            problems.append('%s says %d frames and decodes to %d'
                            % (uid, frames, pixels.shape[0]))
        for index, frame in enumerate(pixels):
            if frame.shape[:2] != expected:
                problems.append('%s frame %d decodes to %s, not %dx%d'
                                % (uid, index, frame.shape, expected[0], expected[1]))
    elif pixels.shape[:2] != expected:
        problems.append('%s decodes to %s, not %dx%d'
                        % (uid, pixels.shape, expected[0], expected[1]))

for uid, frames in sorted(sent.items()):
    if uid not in stored:
        problems.append('%s was sent and is not in the database' % uid)
    elif stored[uid] != frames:
        problems.append('%s was sent with %d frames and holds %d'
                        % (uid, frames, stored[uid]))
for uid in sorted(withheld):
    if uid in stored:
        problems.append('%s failed its sub-operation and is in the database anyway' % uid)
for uid in sorted(set(stored) - set(sent)):
    problems.append('%s is in the database and was never sent' % uid)

print('sent      %d instances, %d frames' % (len(sent), sum(sent.values())))
print('withheld  %d instances, %d frames' % (len(withheld), sum(withheld.values())))
print('stored    %d instances, %d frames' % (len(stored), sum(stored.values())))
print('indexed   %d image rows' % rows)
if sum(stored.values()) != rows:
    problems.append('%d frames on disk and %d rows in the database'
                    % (sum(stored.values()), rows))
for problem in problems:
    print('PROBLEM: %s' % problem)
sys.exit(1 if problems else 0)
