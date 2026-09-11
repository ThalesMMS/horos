#!/usr/bin/env python3
"""Every frame of a multiframe was placed where the first one is.

`-[DCMPix loadDICOMDCMFramework]` reads each frame's own position from
`PerFrameFunctionalGroupsSequence` > `PlanePositionSequence`, through
`-dcmFrameworkLoad0x0020:`, which sets `originX/Y/Z` and `isOriginDefined`. In the
multiframe branch it then read `ImagePositionPatient` again - from `dcmObject`,
the whole object rather than the frame - and overwrote what it had just read:

    [self dcmFrameworkLoad0x0020:object];
    [self dcmFrameworkLoad0x0028:object];

    NSArray *ipp = [dcmObject attributeArrayWithName:@"ImagePositionPatient"];
    if( ipp && [ipp count] >= 3)
    {
        originX = [[ipp objectAtIndex:0] doubleValue];
        …

An Enhanced MR or CT has no object-level `ImagePositionPatient`, so for those the
second read found nothing and the frame's own position stood. A legacy converted
enhanced object does carry one, and for those every frame was placed at the same
point - while the database, which reads the per-frame positions in
`DicomFileDCMTKCategory`, placed them correctly. Two answers to the same
question, from the same file.

This checks the source: `-dcmFrameworkLoad0x0020:` has already read the frame's
position by the time that branch is done, and nothing re-reads it from the
object.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
code = re.sub(r'//[^\n]*', '', pix)

# --- the per-frame position is read from the frame ----------------------------
at = code.find('attributeWithName:@"Per-frameFunctionalGroupsSequence"')
if at < 0:
    failures.append('the per-frame functional groups are no longer read')
else:
    per_frame = code[at:at + 6000]
    position = per_frame.find('attributeWithName:@"PlanePositionSequence"')
    if position < 0:
        failures.append('a frame\'s own position is no longer read')
    else:
        branch = per_frame[position:position + 1400]
        if 'dcmFrameworkLoad0x0020' not in branch:
            failures.append('the frame\'s position is not loaded')
        if 'attributeArrayWithName:@"ImagePositionPatient"' in branch:
            failures.append('the frame\'s position is read and then overwritten with the '
                            'object\'s own, so every frame of a legacy converted enhanced '
                            'object is placed where the first one is')
    if 'attributeWithName:@"PlaneOrientationSequence"' not in per_frame:
        failures.append('a frame that carries its own orientation no longer has it read')

# --- and -dcmFrameworkLoad0x0020: is what reads it ----------------------------
at = code.find('- (void) dcmFrameworkLoad0x0020:')
loader = code[at:at + 2000] if at >= 0 else ''
if not loader:
    failures.append('-dcmFrameworkLoad0x0020: is gone')
else:
    for attribute in ('ImagePositionPatient', 'ImagePositionVolume',
                      'ImageOrientationPatient', 'ImageOrientationVolume'):
        if attribute not in loader:
            failures.append('%s is no longer read where a frame\'s geometry comes from'
                            % attribute)
    if 'isOriginDefined = YES' not in loader:
        failures.append('reading a position no longer marks the origin as known')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print("ok: a frame's position comes from the frame, and is not overwritten by the object's")
