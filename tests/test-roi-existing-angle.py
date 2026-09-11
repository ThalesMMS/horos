#!/usr/bin/env python3
"""Existing tAngle already measures in physical coordinates; do not add a second tool."""
from pathlib import Path
import subprocess
import sys
import tempfile
root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/ROI.m').read_bytes().decode('latin1')
start = source.index('-(float) Angle:(NSPoint) p2 :(NSPoint) p1 :(NSPoint) p3')
i = source.index('{', start) + 1
depth = 1
while depth:
    depth += (source[i] == '{') - (source[i] == '}')
    i += 1
method = source[start:i]
if 'pixelSpacingX' not in method or 'pixelSpacingY' not in method:
    print('FAIL: existing Angle: no longer uses physical spacing', file=sys.stderr)
    sys.exit(1)
code = r'''
#import <Foundation/Foundation.h>
#include <math.h>
#define deg2rad 0.017453292519943295
@interface ROI:NSObject { @public double pixelSpacingX, pixelSpacingY; }
-(float) Angle:(NSPoint)p2 :(NSPoint)p1 :(NSPoint)p3;
@end
@implementation ROI
METHOD
@end
int main() {
    ROI *r = [ROI new];
    r->pixelSpacingX = 1;
    r->pixelSpacingY = 0.5;
    float physical = [r Angle:NSMakePoint(4,0) :NSMakePoint(0,0) :NSMakePoint(4,4)];
    float expected = atan(0.5) * 180 / M_PI;
    if (fabs(physical - expected) > 1e-4) {
        fprintf(stderr, "FAIL: existing Angle: %f wanted %f\n", physical, expected);
        return 1;
    }
    r->pixelSpacingX = r->pixelSpacingY = 1;
    if (fabs([r Angle:NSMakePoint(4,0) :NSMakePoint(0,0) :NSMakePoint(4,4)] - 45) > 1e-4) {
        fprintf(stderr, "FAIL: isotropic Angle:\n");
        return 1;
    }
    puts("PASS: existing tAngle tool already reports the physical angle");
}
'''.replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-roi-angle-') as d:
    p = Path(d)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-framework', 'Foundation', str(p / 'test.m'),
                    '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
