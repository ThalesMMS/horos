#!/usr/bin/env python3
"""#374/A216: a sharpen filter must not move the numbers a ROI reports.

A216 asks for the convolution filter to be reversible in the MPR/CPR
presentation *"sem modificar DICOM original nem valores de medição"*.

The original pixels were safe: `-applyConvolutionOnImage:` writes into a buffer
of its own. The measured values were not. `-getROIValue:::` read
`-computefImage`, and that method applied the convolution before returning:

    if( convolution)
        result = [self applyConvolutionOnImage: result RGB: NO];

so with a sharpen filter on, every mean, minimum, maximum, deviation, median,
skewness and kurtosis was taken over the sharpened pixels. Turning the filter on
to see an edge better changed the number written in the report.

This links the application's own DCMPix.o and measures a ROI with the filter off
and on, and then after the separate, deliberate
`-applyConvolutionOnSourceImage`, which *is* meant to change the pixels.
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

failures = []

pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')

measurement = re.search(r'- \(float\*\)computefImageForMeasurement\s*\{(.*?)\n\}', pix, re.S)
if not measurement:
    failures.append('-computefImageForMeasurement is missing')
else:
    if 'applyConvolution' in measurement.group(1):
        failures.append('the measurement source must not apply the presentation filter')
    if 'computeThickSlab' not in measurement.group(1):
        failures.append('the measurement source must still follow the thick slab: it is the image '
                        'the ROI was drawn on')

display = re.search(r'- \(float\*\)computefImage\s*\{(.*?)\n\}', pix, re.S)
if not display:
    failures.append('-computefImage is missing')
elif 'applyConvolutionOnImage' not in display.group(1):
    failures.append('-computefImage must still apply the filter: the display is what it is for')

getter = pix[pix.find('- (float*) getROIValue:'):]
getter = getter[:getter.find('\n- (')]
if 'computefImageForMeasurement' not in getter:
    failures.append('getROIValue must read the measurement source')
if re.search(r'\[self computefImage\]', getter):
    failures.append('getROIValue still reads the filtered pixels')

PROBE = r'''
#import <Foundation/Foundation.h>
#import "DCMPix.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>

enum { kBrush = 20 };
static const int kSide = 64;

@interface ProbePix : DCMPix
- (void) prepareRamp;
@end
@implementation ProbePix
- (void) CheckLoad {}
- (void) applyShutter {}
- (void) prepareRamp
{
    width = height = kSide; isRGB = NO; thickSlabVRActivated = NO;
    fImage = (float*) calloc( kSide * kSide, sizeof( float));
    baseAddr = (char*) calloc( kSide * kSide, 4);
    pixArray = [[NSArray arrayWithObject: [NSNull null]] retain];
    // Not a flat field: a convolution over constant pixels would change nothing
    // and the test would pass without measuring anything.
    for( int y = 0; y < kSide; y++)
        for( int x = 0; x < kSide; x++)
            fImage[ y * kSide + x] = (float)(x * 3 + y * 7) + ((x / 8 + y / 8) % 2 ? 200 : 0);
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

static int failures = 0;
static void check( bool ok, const char *what)
{
    if( !ok) { fprintf( stderr, "FAIL: %s\n", what); failures++; }
}

// -computeROI::::: reduces exactly this array, and also asks HorosROIStatistics
// for a median and writes it back onto the ROI. Neither is what is under test
// here, and both would need stubs that stand between the measurement and the
// pixels -- so the reduction is done here, over the values the shipped method
// returns.
static void measure( DCMPix *pix, ROI *roi, float *mean, float *minimum, float *maximum)
{
    long count = 0;
    float *values = [pix getROIValue: &count : (id) roi : nil];
    double total = 0;
    float lo = INFINITY, hi = -INFINITY;
    for( long i = 0; i < count; i++)
    {
        total += values[ i];
        if( values[ i] < lo) lo = values[ i];
        if( values[ i] > hi) hi = values[ i];
    }
    *mean = count ? (float)(total / count) : 0;
    *minimum = count ? lo : 0;
    *maximum = count ? hi : 0;
    free( values);
}

int main(){ @autoreleasepool {
    ProbePix *pix = [[ProbePix alloc] init];
    [pix prepareRamp];

    const long side = kSide / 2;
    unsigned char *texture = (unsigned char*) malloc( side * side);
    memset( texture, 1, side * side);
    ROI *roi = [[ROI alloc] init];
    roi.type = kBrush;
    roi.textureBuffer = texture;
    roi.textureWidth = roi.textureHeight = side;
    roi.textureUpLeftCornerX = roi.textureUpLeftCornerY = side / 2;

    float plainMean = 0, plainMin = 0, plainMax = 0;
    measure( pix, roi, &plainMean, &plainMin, &plainMax);

    // A sharpen kernel, the ordinary presentation filter.
    float sharpen[ 9] = { 0, -1, 0, -1, 5, -1, 0, -1, 0};
    [pix setConvolutionKernel: sharpen : 3 : 1];

    // The display must actually change, or nothing below proves anything.
    float *filtered = [pix computefImage];
    long differing = 0;
    if( filtered && filtered != pix.fImage)
    {
        for( long i = 0; i < (long) kSide * kSide; i++)
            if( fabsf( filtered[ i] - pix.fImage[ i]) > 0.001f) differing++;
        free( filtered);
    }
    char message[ 220];
    snprintf( message, sizeof message, "the filter must change the displayed pixels: %ld of %d differ",
              differing, kSide * kSide);
    check( differing > kSide * kSide / 4, message);

    float filteredMean = 0, filteredMin = 0, filteredMax = 0;
    measure( pix, roi, &filteredMean, &filteredMin, &filteredMax);
    snprintf( message, sizeof message,
              "the filter moved the measurement: mean %g -> %g, min %g -> %g, max %g -> %g",
              plainMean, filteredMean, plainMin, filteredMin, plainMax, filteredMax);
    check( filteredMean == plainMean && filteredMin == plainMin && filteredMax == plainMax, message);

    // Turning it off again must not move it either -- "reversible" is the word
    // the criterion uses.
    [pix setConvolutionKernel: nil : 0 : 0];
    float revertedMean = 0, ignoredMin = 0, ignoredMax = 0;
    measure( pix, roi, &revertedMean, &ignoredMin, &ignoredMax);
    snprintf( message, sizeof message, "removing the filter moved the measurement: %g -> %g",
              plainMean, revertedMean);
    check( revertedMean == plainMean, message);

    // The deliberate one does change the pixels, and the measurement follows it.
    [pix setConvolutionKernel: sharpen : 3 : 1];
    [pix applyConvolutionOnSourceImage];
    [pix setConvolutionKernel: nil : 0 : 0];
    float appliedMean = 0, appliedMin = 0, appliedMax = 0;
    measure( pix, roi, &appliedMean, &appliedMin, &appliedMax);
    // A sharpen kernel has unit DC gain, so it leaves the mean of a ramp alone;
    // what it moves is the extremes, which is the point of sharpening.
    snprintf( message, sizeof message,
              "applying the filter to the source must change the measurement: "
              "mean %g -> %g, min %g -> %g, max %g -> %g",
              plainMean, appliedMean, plainMin, appliedMin, plainMax, appliedMax);
    check( appliedMean != plainMean || appliedMin != plainMin || appliedMax != plainMax, message);

    if( failures) { fprintf( stderr, "FAIL: %d check%s\n", failures, failures == 1 ? "" : "s"); return 1; }
    printf( "mean %g and range [%g, %g] unchanged with the filter on, while %ld of %d displayed pixels differ; "
            "applying it to the source gives range [%g, %g]",
            plainMean, plainMin, plainMax, differing, kSide * kSide, appliedMin, appliedMax);
    return 0;
}}
'''

FRAMEWORKS = ['Foundation', 'AppKit', 'AVFoundation', 'CoreData', 'CoreMedia', 'CoreVideo', 'Accelerate']


def objectiveCStubs():
    listing = subprocess.run(['nm', '-u', str(obj)], capture_output=True, text=True, check=True).stdout
    names = sorted({m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)})
    sources = root / 'Horos/Sources'
    declared = [n for n in names
                if n != 'ROI' and ((sources / (n + '.h')).is_file() or (sources / (n + '.m')).is_file()
                                   or (sources / (n + '.mm')).is_file())]
    return ''.join('@interface %s : NSObject @end\n@implementation %s @end\n' % (n, n) for n in declared)


def link(directory, placeholders):
    assembly = ''.join('.globl %s\n%s: .quad 0\n' % (s, s) for s in sorted(placeholders))
    (directory / 'placeholders.s').write_text('.data\n' + assembly)
    command = ['xcrun', 'clang++', '-std=c++11', '-Wno-deprecated-declarations',
               '-I' + str(root / 'Horos/Sources'),
               str(directory / 'probe.mm'), str(directory / 'stubs.mm'),
               str(directory / 'placeholders.s'), str(obj),
               '-Wl,-undefined,dynamic_lookup', '-o', str(directory / 'probe')]
    for framework in FRAMEWORKS:
        command += ['-framework', framework]
    subprocess.run(command, check=True, capture_output=True)


measured = ''
if not failures:
    with tempfile.TemporaryDirectory(prefix='horos-filter-measure-') as name:
        directory = Path(name)
        (directory / 'probe.mm').write_text(PROBE)
        (directory / 'stubs.mm').write_text('#import <Foundation/Foundation.h>\n' + objectiveCStubs())
        placeholders = set()
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
        if run.returncode:
            sys.stderr.write(run.stderr)
            failures.append('a presentation filter still moves the measured values')
        else:
            measured = run.stdout.strip()

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: %s' % measured)
