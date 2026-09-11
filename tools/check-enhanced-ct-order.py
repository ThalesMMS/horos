#!/usr/bin/env python3
"""Does sorting a multiframe by slice location put the frames in geometric order?

Horos sorts a series with `-[DicomSeries sortDescriptorsForImages]`: by
`sliceLocation` then `instanceNumber` when "sort by slice location" is on, and by
`instanceNumber` then `sliceLocation` when it is off. For a multiframe the
instance number is the frame's place in the file, so if the slice locations are
all equal the sort falls back to encoding order whichever way it is set.

This applies the same two orderings to what the database stored, and reads each
frame's own pixels back out of the file to say where that frame actually belongs:
the fixture fills the frame at z = k*spacing with the value 100*k.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import numpy
import pydicom

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture', type=Path, help='the generated enhanced-ct.dcm')
parser.add_argument('database', type=Path, help='the database location Horos was given')
parser.add_argument('--spacing', type=float, default=2.0)
parser.add_argument('--expect-stack-numbers', action='store_true',
                    help='the frames say where they sit in the stack, so the instance numbers '
                         'have to be those and the instance order has to be the geometric one')
arguments = parser.parse_args()

dataset = pydicom.dcmread(str(arguments.fixture))
pixels = dataset.pixel_array
frames = int(dataset.NumberOfFrames)

# Where each frame belongs, according to its own pixels and its own position.
geometry = {}
for index in range(frames):
    fill = int(numpy.unique(pixels[index])[0])
    item = dataset.PerFrameFunctionalGroupsSequence[index]
    position = [float(v) for v in item.PlanePositionSequence[0].ImagePositionPatient]
    # The slice location is the coordinate along the normal of the two direction
    # cosines, which is not always z: a sagittal acquisition advances along x.
    shared = dataset.SharedFunctionalGroupsSequence[0]
    if 'PlaneOrientationSequence' in shared:
        cosines = [float(v) for v in shared.PlaneOrientationSequence[0].ImageOrientationPatient]
    elif 'PlaneOrientationSequence' in item:
        cosines = [float(v) for v in item.PlaneOrientationSequence[0].ImageOrientationPatient]
    else:
        cosines = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    row, column = cosines[:3], cosines[3:]
    normal = [row[1] * column[2] - row[2] * column[1],
              row[2] * column[0] - row[0] * column[2],
              row[0] * column[1] - row[1] * column[0]]
    along = max(range(3), key=lambda axis: abs(normal[axis]))
    geometry[index] = (fill // 100, position[along])

connection = sqlite3.connect(arguments.database / 'Horos Data' / 'Database.sql')
# By this file's own series: a database holding more than one enhanced object
# would otherwise be read as one stack of everything.
rows = connection.execute(
    'select i.ZFRAMEID, i.ZSLICELOCATION, i.ZINSTANCENUMBER from ZIMAGE i '
    'join ZSERIES s on i.ZSERIES = s.Z_PK where s.ZSERIESDICOMUID = ?',
    (str(dataset.SeriesInstanceUID),)).fetchall()
if not rows:
    raise SystemExit('series %s is not in that database' % dataset.SeriesInstanceUID)

# What the acquisition said, if it said anything: the frame's place in its stack.
stack = {}
for index in range(frames):
    item = dataset.PerFrameFunctionalGroupsSequence[index]
    if 'FrameContentSequence' in item and 'InStackPositionNumber' in item.FrameContentSequence[0]:
        stack[index] = int(item.FrameContentSequence[0].InStackPositionNumber)

problems = []
if len(rows) != frames:
    problems.append('%d frames in the file and %d rows in the database' % (frames, len(rows)))

by_location = sorted(rows, key=lambda r: (r[1] if r[1] is not None else 0.0, r[2]))
by_instance = sorted(rows, key=lambda r: (r[2], r[1] if r[1] is not None else 0.0))

expected = [index for index, _ in sorted(geometry.items(), key=lambda kv: kv[1][1])]
sorted_frames = [row[0] for row in by_location]
instance_frames = [row[0] for row in by_instance]

print('frame  fill slice   z      stored sliceLocation  in-stack  instance')
for frame, location, number in sorted(rows, key=lambda r: (r[0] if r[0] is not None else -1)):
    slice_index, z = geometry[frame]
    print('  %2d   %4d  %2d   %6.1f   %-14s %-9s %s'
          % (frame, slice_index * 100, slice_index, z, location,
             stack.get(frame, '(none)'), number))
print()
print('geometric order      %s' % expected)
print('sorted by location   %s' % sorted_frames)
print('sorted by instance   %s' % instance_frames)

if sorted_frames != expected:
    problems.append('sorting by slice location gives %s, not the geometric %s'
                    % (sorted_frames, expected))
distinct = {row[1] for row in rows}
if len(distinct) == 1:
    problems.append('every frame was stored with the same slice location %r, so only the '
                    'encoding order is left to sort by' % distinct.pop())
for frame, location, _ in rows:
    z = geometry[frame][1]
    if location is None or abs(location - z) > 1e-3:
        problems.append('frame %d is at z=%.1f and was stored as %r' % (frame, z, location))

if arguments.expect_stack_numbers:
    for frame, _, number in rows:
        if frame not in stack:
            problems.append('frame %d carries no in-stack position and one was expected' % frame)
        elif number != stack[frame]:
            problems.append('frame %d sits at %d in its stack and was numbered %r'
                            % (frame, stack[frame], number))
    if instance_frames != expected:
        problems.append('sorting by instance gives %s, not the geometric %s'
                        % (instance_frames, expected))
elif stack:
    # Repeated or absent numbers: the frame index is all there is, and the order it
    # gives has to stay the file's own.
    if instance_frames != sorted(instance_frames):
        problems.append('with no usable stack numbers the instance order is %s, not the file '
                        'order' % instance_frames)

for problem in problems:
    print('PROBLEM: %s' % problem)
sys.exit(1 if problems else 0)
