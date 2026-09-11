#!/usr/bin/env python3
"""Check what `-[DCMPix getROIValue:::]` leaves behind on its short paths.

The method has two output parameters and several early exits. Both callers in
the application read `locations` and the count before testing the returned
pointer, so a path that leaves them untouched hands back whatever the caller's
stack happened to hold. The greyscale conversion in its brush branch is also
checked here, because it read different bytes of the pixel than every other
loop in the same file and divided only the last of the three.

Like the scanline test, this links the DCMPix.o the application is built from
and subclasses the real class, so it measures the shipped method.
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

PROBE = r'''
#import <Foundation/Foundation.h>
#import "DCMPix.h"
#include <cstdio>
#include <cstdlib>

enum { kOpenPolygon = 10, kBrush = 20 };   // ToolMode, DCMView.h

@interface ProbePix : DCMPix
- (void) prepareWidth:(long)w height:(long)h rgb:(BOOL)rgb;
@end
@implementation ProbePix
// The filler only needs pixels; loading them from a file is not what is under
// test here.
- (void) CheckLoad {}
// The real method returns fImage when no thick slab is active, and its caller
// frees the buffer only when it differs from fImage.
- (float*) computefImage { return fImage; }
- (void) prepareWidth:(long)w height:(long)h rgb:(BOOL)rgb
{
    width = w; height = h; isRGB = rgb; thickSlabVRActivated = NO;
    // -dealloc would free both of these, so each instance owns its own.
    fImage = (float*) calloc( w * h, sizeof( float));
    baseAddr = (char*) calloc( w * h, 4);
    // The filler refuses a slice count of zero; only the count is read here.
    pixArray = [[NSArray arrayWithObject: [NSNull null]] retain];
}
@end

@interface ProbePoint : NSObject
@property (assign) NSPoint point;
@end
@implementation ProbePoint
@end

// Stands in for ROI: getROIValue only asks it for its type, its spline and,
// for a brush, its texture.
@interface ROI : NSObject
@property (assign) long type;
@property (retain) NSMutableArray *spline;
@property (assign) unsigned char *textureBuffer;
@property (assign) long textureWidth, textureHeight;
@property (assign) long textureUpLeftCornerX, textureUpLeftCornerY;
@end
@implementation ROI
- (NSMutableArray*) splinePoints { return self.spline; }
@end

static ROI *polygonWith( int count)
{
    ROI *roi = [[ROI alloc] init];
    roi.type = kOpenPolygon;
    NSMutableArray *points = [NSMutableArray array];
    for( int i = 0; i < count; i++) {
        ProbePoint *point = [[ProbePoint alloc] init];
        // A square, so more than two points enclose real pixels.
        point.point = NSMakePoint( (i == 1 || i == 2) ? 8 : 3, (i >= 2) ? 8 : 3);
        [points addObject: point];
    }
    roi.spline = points;
    return roi;
}

static int failures = 0;
static void check( bool ok, const char *what)
{
    if( !ok) { fprintf( stderr, "FAIL: %s\n", what); failures++; }
}

// A pointer and a count the method must overwrite rather than leave alone.
static float * const kUnwritten = (float*) 0x1234;
static const long kUncounted = 4242;

static void shortPath( int pointCount, const char *label)
{
    ProbePix *pix = [[ProbePix alloc] init];
    [pix prepareWidth: 16 height: 16 rgb: NO];
    float *locations = kUnwritten;
    long count = kUncounted;
    float *values = [pix getROIValue: &count : (id) polygonWith( pointCount) : &locations];
    char message[ 160];
    snprintf( message, sizeof message, "%s: locations left as %p", label, (void*) locations);
    check( locations != kUnwritten, message);
    snprintf( message, sizeof message, "%s: count left as %ld", label, count);
    check( count != kUncounted, message);
    if( values == nil)
        check( locations == nil && count == 0,
               "a call that returns no values must report none");
    free( values);
    if( locations != kUnwritten) free( locations);
}

int main(){ @autoreleasepool {
    // Fewer than three points enclose nothing, and no spline at all is the
    // early return before the assignments at the end of the method.
    shortPath( 0, "no spline point");
    shortPath( 2, "two spline points");

    // The ordinary path still has to produce values and coordinates.
    {
        ProbePix *pix = [[ProbePix alloc] init];
        [pix prepareWidth: 16 height: 16 rgb: NO];
        float *locations = kUnwritten;
        long count = kUncounted;
        float *values = [pix getROIValue: &count : (id) polygonWith( 4) : &locations];
        char message[ 160];
        snprintf( message, sizeof message,
                  "a four point polygon must return values and coordinates: values=%p locations=%p count=%ld",
                  (void*) values, (void*) locations, count);
        check( values != nil && locations != nil && locations != kUnwritten && count > 0, message);
        free( values);
        if( locations && locations != kUnwritten) free( locations);
    }

    // A brush over RGB pixels: the mean of the three colour bytes, read the
    // way the rest of DCMPix.m reads them.
    {
        const unsigned char pixel[ 4] = {200, 30, 60, 90};   // first byte is not colour
        ProbePix *pix = [[ProbePix alloc] init];
        [pix prepareWidth: 16 height: 16 rgb: YES];
        memcpy( pix.baseAddr, pixel, sizeof pixel);
        unsigned char texture = 1;
        ROI *roi = [[ROI alloc] init];
        roi.type = kBrush;
        roi.textureBuffer = &texture;
        roi.textureWidth = 1; roi.textureHeight = 1;
        roi.textureUpLeftCornerX = 0; roi.textureUpLeftCornerY = 0;
        float *locations = kUnwritten;
        long count = kUncounted;
        float *values = [pix getROIValue: &count : (id) roi : &locations];
        const float expected = (pixel[ 1] + pixel[ 2] + pixel[ 3]) / 3.f;
        if( values == nil || count != 1)
            check( false, "a one pixel brush must return one value");
        else {
            char message[ 160];
            snprintf( message, sizeof message, "RGB brush value is %g, expected %g",
                      values[ 0], expected);
            check( values[ 0] == expected, message);
        }
        free( values);
        if( locations && locations != kUnwritten) free( locations);
    }

    if( failures) { fprintf( stderr, "FAIL: %d check%s\n", failures, failures == 1 ? "" : "s"); return 1; }
    puts( "PASS: output parameters written on every path and the RGB brush value is the mean of the colour bytes");
    return 0;
}}
'''

FRAMEWORKS = ['Foundation', 'AppKit', 'AVFoundation', 'CoreData', 'CoreMedia', 'CoreVideo']


def objectiveCStubs():
    """Classes DCMPix.m names that no linked framework defines.

    Class references are fixed up when the image loads, so these need real
    classes. ROI is declared by the probe itself.
    """
    listing = subprocess.run(['nm', '-u', str(obj)], capture_output=True, text=True, check=True).stdout
    names = sorted({m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)})
    sources = root / 'Horos/Sources'
    declared = [n for n in names
                if n != 'ROI' and ((sources / (n + '.h')).is_file() or (sources / (n + '.m')).is_file()
                                   or (sources / (n + '.mm')).is_file())]
    return ''.join('@interface %s : NSObject @end\n@implementation %s @end\n' % (n, n) for n in declared)


def link(directory, placeholders):
    """Link the probe, listing `placeholders` as bare addresses.

    Symbols resolved from the application's other objects and from vendored
    archives are never reached by this method, so an address is enough and the
    test does not have to track their signatures.
    """
    assembly = ''.join('.globl %s\n%s: .quad 0\n' % (s, s) for s in sorted(placeholders))
    (directory / 'placeholders.s').write_text('.data\n' + assembly)
    # Manual retain/release, like DCMPix.m itself: the probe hands the real
    # class its buffers and never releases it, so nothing is freed twice.
    command = ['xcrun', 'clang++', '-std=c++11', '-Wno-deprecated-declarations',
               '-I' + str(root / 'Horos/Sources'),
               str(directory / 'probe.mm'), str(directory / 'stubs.mm'),
               str(directory / 'placeholders.s'), str(obj),
               '-Wl,-undefined,dynamic_lookup', '-o', str(directory / 'probe')]
    for framework in FRAMEWORKS:
        command += ['-framework', framework]
    subprocess.run(command, check=True, capture_output=True)


with tempfile.TemporaryDirectory(prefix='horos-roi-value-') as name:
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
