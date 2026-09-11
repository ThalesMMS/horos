#!/usr/bin/env python3
"""Check that the ROI scanline filler reports the same coordinates for RGB pixels.

`ras_FillPolygon` walks a polygon and, when asked, writes one (x, y) pair per
covered pixel. It has two inner loops, one per pixel format, and `getROIValue`
picks between them from the series. A coordinate is a property of the polygon,
so the two loops have to agree; `createLayerROIFromROI:` sizes a bitmap from the
Y range and the calcium scoring overlap test compares Y between ROIs, so a
constant Y is a wrong bitmap and a wrong overlap rather than a visible error.

This links the object file the application itself is built from, so it measures
the shipped filler and not a copy of it.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
objects = [root / 'build/Build/Intermediates.noindex/Horos.build' / configuration /
           'Horos.build/Objects-normal/arm64/DCMPix.o'
           for configuration in ('Debug', 'Release')]
obj = next((o for o in objects if o.is_file()), None)
if obj is None:
    print('needs a built DCMPix.o in %s' % ' or '.join(str(o) for o in objects), file=sys.stderr)
    raise SystemExit(2)

# The polygon is a rectangle, so every covered pixel's row is known in advance
# and the test does not have to trust either loop to produce the expectation.
LEFT, RIGHT, TOP, BOTTOM, WIDTH, HEIGHT = 2, 6, 3, 6, 10, 10
PROBE = r'''
#import <Foundation/Foundation.h>
#include <cstdio>
#include <cstdlib>
typedef struct { long x, y; } NSPointInt;
extern "C" void ras_FillPolygon( NSPointInt *p, long no, float *pix, long w, long h, long s,
    float min, float max, BOOL outside, float newVal, BOOL addition, BOOL RGB, BOOL compute,
    float *imax, float *imin, long *count, float *itotal, float *idev, float imean,
    long orientation, long stackNo, BOOL restore, float *values, float *locations);
static const long kLeft = %(left)d, kRight = %(right)d, kTop = %(top)d, kBottom = %(bottom)d;
static const long kWidth = %(width)d, kHeight = %(height)d;
static void fill( BOOL rgb, float **locations, long *count)
{
    // Four bytes per pixel either way: the RGB loop reads this buffer as bytes.
    float *pix = (float*) calloc( kWidth * kHeight, sizeof( float));
    NSPointInt pts[ 4] = {{kLeft, kTop}, {kRight, kTop}, {kRight, kBottom}, {kLeft, kBottom}};
    float *values = (float*) calloc( kWidth * kHeight, sizeof( float));
    *locations = (float*) calloc( kWidth * kHeight * 2, sizeof( float));
    *count = 0;
    ras_FillPolygon( pts, 4, pix, kWidth, kHeight, 1, 0, 0, NO, 0, NO, rgb, YES, nil, nil,
                     count, nil, nil, 0, 2, 0, NO, values, *locations);
    free( values);
    free( pix);
}
int main(){ @autoreleasepool {
    float *grey = nil, *rgb = nil;
    long greyCount = 0, rgbCount = 0;
    fill( NO, &grey, &greyCount);
    fill( YES, &rgb, &rgbCount);
    if( greyCount == 0 || greyCount != rgbCount) {
        fprintf( stderr, "FAIL: %%ld greyscale points and %%ld RGB points\n", greyCount, rgbCount);
        return 1;
    }
    int failures = 0;
    long index = 0;
    for( long y = kTop; y <= kBottom; y++) {
        for( long x = kLeft; x <= kRight; x++, index++) {
            if( index >= greyCount) break;
            const float *pair[ 2] = {grey + 2 * index, rgb + 2 * index};
            const char *name[ 2] = {"greyscale", "RGB"};
            for( int which = 0; which < 2; which++) {
                if( pair[ which][ 0] != (float) x || pair[ which][ 1] != (float) y) {
                    if( failures < 8)
                        fprintf( stderr, "FAIL: %%s point %%ld is (%%g, %%g), expected (%%ld, %%ld)\n",
                                 name[ which], index, pair[ which][ 0], pair[ which][ 1], x, y);
                    failures++;
                }
            }
        }
    }
    const long expected = (kRight - kLeft + 1) * (kBottom - kTop + 1);
    if( greyCount != expected) {
        fprintf( stderr, "FAIL: %%ld points cover a %%ld pixel rectangle\n", greyCount, expected);
        return 1;
    }
    free( grey);
    free( rgb);
    if( failures) {
        fprintf( stderr, "FAIL: %%d of %%ld coordinates wrong\n", failures, 2 * greyCount);
        return 1;
    }
    printf( "PASS: %%ld scanline coordinates identical and correct in both pixel formats\n", greyCount);
    return 0;
}}
''' % dict(left=LEFT, right=RIGHT, top=TOP, bottom=BOTTOM, width=WIDTH, height=HEIGHT)

FRAMEWORKS = ['Foundation', 'AppKit', 'AVFoundation', 'CoreData', 'CoreMedia', 'CoreVideo']


def objectiveCStubs():
    """Classes DCMPix.m names that no linked framework defines.

    The runtime fixes class references up when the image loads, so these need a
    real class and not a placeholder address. A class the project declares is
    one the frameworks cannot supply.
    """
    listing = subprocess.run(['nm', '-u', str(obj)], capture_output=True, text=True, check=True).stdout
    names = sorted({m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)})
    sources = root / 'Horos/Sources'
    declared = set()
    for name in names:
        if list(sources.glob(name + '.h')) or list(sources.glob(name + '.mm')) or (sources / (name + '.m')).is_file():
            declared.add(name)
    return ''.join('@interface %s : NSObject @end\n@implementation %s @end\n' % (n, n) for n in sorted(declared))


def link(directory, placeholders):
    """Link the probe, listing `placeholders` as bare addresses.

    Symbols the application resolves from its own other objects and from
    vendored archives are never reached by the filler, so an address is enough
    and the test does not have to track their signatures.
    """
    assembly = ''.join('.globl %s\n%s: .quad 0\n' % (s, s) for s in sorted(placeholders))
    (directory / 'placeholders.s').write_text('.data\n' + assembly if placeholders else '.data\n')
    command = ['xcrun', 'clang++', '-std=c++11', '-fobjc-arc',
               str(directory / 'probe.mm'), str(directory / 'stubs.mm'),
               str(directory / 'placeholders.s'), str(obj),
               '-Wl,-undefined,dynamic_lookup', '-o', str(directory / 'probe')]
    for framework in FRAMEWORKS:
        command += ['-framework', framework]
    subprocess.run(command, check=True, capture_output=True)


with tempfile.TemporaryDirectory(prefix='horos-roi-scanline-') as name:
    directory = Path(name)
    (directory / 'probe.mm').write_text(PROBE)
    (directory / 'stubs.mm').write_text('#import <Foundation/Foundation.h>\n' + objectiveCStubs())
    placeholders = set()
    # dyld names one missing symbol per attempt, so collect them by running.
    for _ in range(200):
        link(directory, placeholders)
        run = subprocess.run([str(directory / 'probe')], capture_output=True, text=True)
        missing = re.search(r"symbol not found in flat namespace '([^']+)'", run.stderr)
        if not missing:
            break
        if missing.group(1) in placeholders:
            print('cannot satisfy %s' % missing.group(1), file=sys.stderr)
            raise SystemExit(1)
        placeholders.add(missing.group(1))
    else:
        print('too many unresolved symbols in %s' % obj, file=sys.stderr)
        raise SystemExit(1)
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    raise SystemExit(run.returncode)
