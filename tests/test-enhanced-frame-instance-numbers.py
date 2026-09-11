#!/usr/bin/env python3
""""Sort by instance" numbered a multiframe's frames by where they were stored.

`DicomDatabase` gave frame *f* of a multiframe the instance number
`imageID + f` - the file's own instance number plus the frame's place in the
file. So for a multiframe, sorting by instance number reproduced the encoding
order, whatever the acquisition had said about where each frame sits.

An Enhanced object says it in `PerFrameFunctionalGroupsSequence` >
`FrameContentSequence` > `InStackPositionNumber`. Measured on an Enhanced MR of 8
frames written interleaved, 2 mm apart:

    frame  slice   z     in-stack  instance      before        after
      0      1     2.0      2         2            1            2
      4      0     0.0      1         1            5            1
      …
    sorted by instance   [0,1,2,3,4,5,6,7]   ->   [4,0,5,1,6,2,7,3]
    sorted by location   [4,0,5,1,6,2,7,3]        [4,0,5,1,6,2,7,3]

The two criteria now agree with the geometry when the acquisition numbers its own
frames, and remain distinct when it does not: an object that says nothing, or one
whose stacks each start from one, keeps the frame index, because a repeated
number sorts no better than the file order does.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
reader = (root / 'Horos/Sources/DicomFileDCMTKCategory.mm').read_bytes().decode('latin1')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
series = (root / 'Horos/Sources/DicomSeries.m').read_bytes().decode('latin1')


def body(signature, source):
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


# --- the acquisition's own numbering is read ---------------------------------
code = re.sub(r'//[^\n]*', '', reader)
if 'DCM_FrameContentSequence' not in code or 'DCM_InStackPositionNumber' not in code:
    failures.append('nothing reads where each frame sits in its stack, so a multiframe is '
                    'numbered by the order it happens to be stored in')
if 'instanceNumberArray' not in code:
    failures.append('the per-frame numbers never reach the database')
else:
    at = code.find('instanceNumberArray')
    guard = code[max(at - 400, 0):at + 100]
    if 'NSSet' not in guard or 'NoOfFrames' not in guard:
        failures.append('the per-frame numbers are published without checking that there is one '
                        'per frame and that no two repeat, so an object with several stacks - '
                        'each numbered from one - would sort by a number that means nothing')

# --- and it is what the image row is numbered with ---------------------------
add = body('-(void)addFilesDescribedInDictionaries:', database) or database
at = add.find('instanceNumberArray')
if at < 0:
    failures.append('the database still numbers every frame by its place in the file')
else:
    window = add[at - 200:at + 400]
    if 'instanceNumber' not in window:
        failures.append('the per-frame numbers are read and then not used as the instance number')
    # The fallback has to survive: an object that says nothing keeps the frame index.
    if 'instanceNumber + f' not in add:
        failures.append('a multiframe that says nothing about its frames no longer gets one '
                        'number per frame at all')

# --- the two orders stay distinct and both are named --------------------------
descriptors = body('- (NSArray*) sortDescriptorsForImages', series)
if not descriptors:
    failures.append('-sortDescriptorsForImages is gone')
else:
    if 'sortSeriesBySliceLocation' not in descriptors:
        failures.append('the choice between the two orders is no longer explicit')
    for key in ('instanceNumber', 'sliceLocation'):
        if key not in descriptors:
            failures.append('%s is no longer one of the criteria' % key)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a multiframe frame is numbered by where the acquisition says it sits, and by its '
      'place in the file only when the acquisition says nothing usable')
