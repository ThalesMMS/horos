#!/usr/bin/env python3
"""The generated Swift header must not change legacy untyped MyPoint messages.

A patient-point getter named `x` returning Double collides with MyPoint's Float
getter in Objective-C's global selector pool. On arm64 an untyped NSArray read
then uses the wrong return ABI and a nonzero ROI length collapses to zero.
An optional controller source path exercises the pre-fix regression.
"""
from pathlib import Path
import argparse
import subprocess
import sys
import tempfile
root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('controller', nargs='?', type=Path,
                    default=root/'Horos/Sources/PatientCrosshairController.swift')
parser.add_argument('--host-header', type=Path,
                    help='Also compile the legacy reads with a full generated app header')
args = parser.parse_args()
controller = args.controller
driver = r'''
#import "Horos-Swift.h"
#import "MyPoint.h"
#include <math.h>
#include <stdio.h>
int main(void) { @autoreleasepool {
    NSArray *points = @[[MyPoint point:NSMakePoint(7.491527,5.886186)],
                        [MyPoint point:NSMakePoint(3.401547,17.33813)]];
    // Deliberately untyped: this is how the legacy ROI code reads its points.
    double x = [[points objectAtIndex:0] x], y = [[points objectAtIndex:0] y];
    double dx = [[points objectAtIndex:0] x] - [[points objectAtIndex:1] x];
    double dy = [[points objectAtIndex:0] y] - [[points objectAtIndex:1] y];
    if (fabs(x-7.491527)>1e-5 || fabs(y-5.886186)>1e-5 || hypot(dx,dy)<12) {
        fprintf(stderr,"FAIL: legacy point ABI read x=%g y=%g length=%g\n",x,y,hypot(dx,dy)); return 1;
    }
    puts("PASS: Swift patient-point header preserves Float MyPoint messages and nonzero ROI length");
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-crosshair-objc-') as temporary:
    work=Path(temporary); (work/'Check.m').write_text(driver)
    subprocess.run(['xcrun','swiftc','-emit-library','-module-name','Horos',
                    '-emit-objc-header-path',str(work/'Horos-Swift.h'),
                    str(root/'Horos/Sources/VolumeSession.swift'),
                    str(root/'Horos/Sources/ViewerReferenceLines.swift'),str(controller),
                    str(root/'Horos/Sources/ROIIntersliceGeometry.swift'),
                    str(root/'Horos/Sources/SRSurfacePointGeometry.swift'),
                    str(root/'Horos/Sources/VRInteractionGeometry.swift'),
                    '-o',str(work/'libHoros.dylib')],check=True)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-I'+str(root/'Horos/Sources'),
                    str(work/'Check.m'),str(root/'Horos/Sources/MyPoint.m'),
                    '-framework','Foundation','-L'+str(work),'-lHoros','-o',str(work/'check')],check=True)
    subprocess.run([str(work/'check')],check=True)
    if args.host_header:
        # No Swift object is used by the driver: the full header changes only
        # selector resolution, exactly as it does when compiling legacy ROI.m.
        (work/'Horos-Swift.h').write_bytes(args.host_header.read_bytes())
        subprocess.run(['xcrun','clang','-fno-objc-arc','-fmodules','-I'+str(root/'Horos/Sources'),
                        str(work/'Check.m'),str(root/'Horos/Sources/MyPoint.m'),
                        '-framework','AppKit','-o',str(work/'check-host')],check=True)
        subprocess.run([str(work/'check-host')],check=True)
