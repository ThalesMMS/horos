#!/usr/bin/env python3
"""An enhanced object's window comes from its functional groups, and is read.

PS 3.3 C.7.6.16.2.10: an Enhanced MR or CT states Window Center and Width in
`FrameVOILUTSequence`, inside the shared or the per-frame functional groups, and
not at the top level. Nothing read that sequence, so the window the acquisition
chose was replaced by one computed from the pixels.

Underneath it was a second defect that would have kept the first one hidden:
-[DCMPix dcmFrameworkLoad0x0028:] decided whether an object is PALETTE with
`[[dcmObject attributeValueWithName:@"PhotometricInterpretation"]
  rangeOfString:@"PALETTE"].location != NSNotFound`, and -rangeOfString: sent to
nil answers {0, 0}. Zero is not NSNotFound, so an object that states no
Photometric Interpretation was read as PALETTE. That method is also called for
the nested items of an enhanced object - pixel measures, the plane position, the
frame's VOI LUT - and none of them carries one, so the first nested item turned
isRGB on for the rest of the load. Window Center and Width are read in the same
method under `isRGB == NO`.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
failures = []

# The sequence is read where it lives: once for the whole object, and again for
# the frame, so that a frame stating its own window keeps it.
if pix.count('attributeWithName:@"FrameVOILUTSequence"') != 2:
    failures.append('the frame VOI LUT sequence is not read in both functional groups')
if 'sequenceItem attributeWithName:@"FrameVOILUTSequence"' not in pix:
    failures.append('the shared functional group does not carry the window')

# The per-frame read has to come after the shared one.
shared = pix.find('attributeWithName:@"FrameVOILUTSequence"')
perframe = pix.find('attributeWithName:@"FrameVOILUTSequence"', shared + 1)
transformation = pix.find('attributeWithName:@"PixelValueTransformationSequence"', shared)
if not (shared < transformation < perframe):
    failures.append('the per-frame window is not read after the shared one')

# And the nil comparison is gone.
if '[[dcmObject attributeValueWithName:@"PhotometricInterpretation"] rangeOfString:@"PALETTE"]' in pix:
    failures.append('an object that states no Photometric Interpretation is still read as PALETTE')
if 'photometricInterpretation.length && [photometricInterpretation rangeOfString:@"PALETTE"]' not in pix:
    failures.append('the PALETTE test no longer checks that there is a string to test')

# What -rangeOfString: on nil actually answers, so the reason above is not a
# claim but a measurement.
program = r'''
#import <Foundation/Foundation.h>
int main(void) { @autoreleasepool {
    NSString *absent = nil;
    NSRange range = [absent rangeOfString: @"PALETTE"];
    if (range.location != 0 || range.length != 0) { fprintf(stderr, "nil answered {%lu, %lu}\n",
        (unsigned long) range.location, (unsigned long) range.length); return 1; }
    if (range.location == NSNotFound) { fprintf(stderr, "nil answered NSNotFound\n"); return 1; }
    NSString *present = @"MONOCHROME2";
    if ([present rangeOfString: @"PALETTE"].location != NSNotFound) {
        fprintf(stderr, "MONOCHROME2 matched PALETTE\n"); return 1; }
    printf("ok: rangeOfString: on nil answers {0, 0}, which is not NSNotFound\n");
    return 0;
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-enhanced-window-') as tmp:
    p = Path(tmp)
    (p / 'nil.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', str(p / 'nil.m'), '-framework', 'Foundation',
                    '-o', str(p / 'nil')], check=True)
    subprocess.run([str(p / 'nil')], check=True)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the window is read from the shared and the per-frame functional groups, and an '
      'object with no Photometric Interpretation is no longer read as PALETTE')
