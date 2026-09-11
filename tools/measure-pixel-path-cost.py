#!/usr/bin/env python3
"""Time the per-frame pixel work a scroll pays (#373, A111).

A111 asks for the cost of scroll to be measured. Part of that cost is on the
GPU, where this cannot reach: the texture upload and the `GL_LINEAR`
interpolation need a context and a window. The rest is CPU work in `DCMPix`, and
that is measurable against the application's own object file:

  * `-compute8bitRepresentation`, which rebuilds the 8-bit display cache from
    `fImage` and runs once per frame whenever the window level or the cache has
    been invalidated -- the greyscale path through `vImageConvert_PlanarFtoPlanar8`
    and the RGB path through `vImageTableLookUp_ARGB8888`;
  * `-getROIValue:::`, the measurement path, timed with the cache clean and with
    it stale, which is what the A111 invalidation costs whoever measures.

This is a measurement, not a test: it prints numbers and never fails on them.
Timings depend on the machine and say so.
"""
from pathlib import Path
import argparse
import platform
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
objects = [root / 'build/Build/Intermediates.noindex/Horos.build' / configuration /
           'Horos.build/Objects-normal/arm64/DCMPix.o'
           for configuration in ('Release', 'Debug')]

PROBE = r'''
#import <Foundation/Foundation.h>
#import "DCMPix.h"
#include <cstdio>
#include <cstdlib>
#include <mach/mach_time.h>

static const int kSide = %(side)d;
static const int kRuns = %(runs)d;

enum { kBrush = 20 };

@interface ProbePix : DCMPix
- (void) prepareRGB:(BOOL) rgb;
@end
@implementation ProbePix
- (void) CheckLoad {}
- (float*) computefImage { return fImage; }
- (void) applyShutter {}
- (void) prepareRGB:(BOOL) rgb
{
    width = height = kSide; isRGB = rgb; thickSlabVRActivated = NO;
    fImage = (float*) calloc( kSide * kSide, sizeof( float));
    baseAddr = (char*) calloc( kSide * kSide, 4);
    pixArray = [[NSArray arrayWithObject: [NSNull null]] retain];
    unsigned char *bytes = (unsigned char*) fImage;
    for( long i = 0; i < kSide * (long) kSide; i++)
    {
        if( rgb) { bytes[i*4] = 255; bytes[i*4+1] = i & 255; bytes[i*4+2] = (i>>2) & 255; bytes[i*4+3] = (i>>4) & 255; }
        else fImage[ i] = (float)(i %% 1000);
    }
}
@end

@interface ROI : NSObject
@property (assign) long type;
@property (assign) unsigned char *textureBuffer;
@property (assign) long textureWidth, textureHeight;
@property (assign) long textureUpLeftCornerX, textureUpLeftCornerY;
@end
@implementation ROI
- (NSMutableArray*) splinePoints { return nil; }
@end

static double milliseconds( uint64_t elapsed)
{
    static mach_timebase_info_data_t info;
    if( info.denom == 0) mach_timebase_info( &info);
    return (double) elapsed * info.numer / info.denom / 1.0e6;
}

int main(){ @autoreleasepool {
    printf( "%%d runs at %%d x %%d\n", kRuns, kSide, kSide);

    for( int rgb = 0; rgb < 2; rgb++)
    {
        ProbePix *pix = [[ProbePix alloc] init];
        [pix prepareRGB: rgb ? YES : NO];
        [pix changeWLWW: 127 : 256];
        [pix compute8bitRepresentation];        // warm

        uint64_t start = mach_absolute_time();
        for( int i = 0; i < kRuns; i++)
            [pix compute8bitRepresentation];
        double total = milliseconds( mach_absolute_time() - start);
        printf( "compute8bitRepresentation %%-10s %%8.4f ms per frame\n",
                rgb ? "RGB" : "greyscale", total / kRuns);
    }

    // The measurement path, clean cache and stale cache. The difference is what
    // the A111 invalidation costs a ROI taken after a coloured draw.
    {
        ProbePix *pix = [[ProbePix alloc] init];
        [pix prepareRGB: YES];
        [pix changeWLWW: 127 : 256];

        const long side = kSide / 2;
        unsigned char *texture = (unsigned char*) malloc( side * side);
        memset( texture, 1, side * side);
        ROI *roi = [[ROI alloc] init];
        roi.type = kBrush;
        roi.textureBuffer = texture;
        roi.textureWidth = roi.textureHeight = side;
        roi.textureUpLeftCornerX = roi.textureUpLeftCornerY = 0;

        long count = 0;
        free( [pix getROIValue: &count : (id) roi : nil]);   // warm

        uint64_t start = mach_absolute_time();
        for( int i = 0; i < kRuns; i++)
            free( [pix getROIValue: &count : (id) roi : nil]);
        double clean = milliseconds( mach_absolute_time() - start) / kRuns;

        start = mach_absolute_time();
        for( int i = 0; i < kRuns; i++)
        {
            pix.needToCompute8bitRepresentation = YES;
            free( [pix getROIValue: &count : (id) roi : nil]);
        }
        double stale = milliseconds( mach_absolute_time() - start) / kRuns;

        printf( "getROIValue over %%ld pixels, clean cache      %%8.4f ms\n", (long) count, clean);
        printf( "getROIValue over %%ld pixels, cache invalidated %%8.4f ms\n", (long) count, stale);
        printf( "the A111 invalidation costs a measurement     %%8.4f ms\n", stale - clean);
    }
    return 0;
}}
'''

FRAMEWORKS = ['Foundation', 'AppKit', 'AVFoundation', 'CoreData', 'CoreMedia', 'CoreVideo']


def objectiveCStubs(obj):
    listing = subprocess.run(['nm', '-u', str(obj)], capture_output=True, text=True, check=True).stdout
    names = sorted({m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)})
    sources = root / 'Horos/Sources'
    declared = [n for n in names
                if n != 'ROI' and ((sources / (n + '.h')).is_file() or (sources / (n + '.m')).is_file()
                                   or (sources / (n + '.mm')).is_file())]
    return ''.join('@interface %s : NSObject @end\n@implementation %s @end\n' % (n, n) for n in declared)


def link(directory, obj, placeholders):
    assembly = ''.join('.globl %s\n%s: .quad 0\n' % (s, s) for s in sorted(placeholders))
    (directory / 'placeholders.s').write_text('.data\n' + assembly)
    command = ['xcrun', 'clang++', '-std=c++11', '-O2', '-Wno-deprecated-declarations',
               '-I' + str(root / 'Horos/Sources'),
               str(directory / 'probe.mm'), str(directory / 'stubs.mm'),
               str(directory / 'placeholders.s'), str(obj),
               '-Wl,-undefined,dynamic_lookup', '-o', str(directory / 'probe')]
    for framework in FRAMEWORKS:
        command += ['-framework', framework]
    subprocess.run(command, check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--side', type=int, default=512, help='image side in pixels')
    parser.add_argument('--runs', type=int, default=200)
    arguments = parser.parse_args()

    obj = next((o for o in objects if o.is_file()), None)
    if obj is None:
        print('needs a built DCMPix.o in %s' % ' or '.join(str(o) for o in objects), file=sys.stderr)
        return 2
    print('%s, %s, %s' % (platform.platform(), platform.machine(), obj.parts[-5]))

    with tempfile.TemporaryDirectory(prefix='horos-pixel-cost-') as name:
        directory = Path(name)
        (directory / 'probe.mm').write_text(PROBE % {'side': arguments.side, 'runs': arguments.runs})
        (directory / 'stubs.mm').write_text('#import <Foundation/Foundation.h>\n' + objectiveCStubs(obj))
        placeholders = set()
        for _ in range(200):
            link(directory, obj, placeholders)
            run = subprocess.run([str(directory / 'probe')], capture_output=True, text=True)
            missing = re.search(r"symbol not found in flat namespace '([^']+)'", run.stderr)
            if not missing:
                break
            if missing.group(1) in placeholders:
                print('cannot satisfy %s' % missing.group(1), file=sys.stderr)
                return 1
            placeholders.add(missing.group(1))
        else:
            print('too many unresolved symbols in %s' % obj, file=sys.stderr)
            return 1
        sys.stdout.write(run.stdout)
        sys.stderr.write(run.stderr)
        return run.returncode


if __name__ == '__main__':
    raise SystemExit(main())
