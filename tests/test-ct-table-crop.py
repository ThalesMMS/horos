#!/usr/bin/env python3
"""#373/A255: crop a synthetic CT table away, and measure that it went.

A255 (from #255) asks for a table crop executed on a synthetic table, in a tool
mode that supports it. The supported modes are the ones
`HorosToolModeCapability` marks as drawing ROIs; the brush, `tPlain`, is one of
them, and its fill path in `-[DCMPix fillROI:...]` is the one the Set Pixel
Values sheet reaches through `-roiSetPixels:::::::`.

So this builds the phantom that `tools/generate-ct-table-fixture.py` writes --
same geometry, checked against that file so the two cannot drift -- puts a brush
ROI over the patient, and asks the application's own `DCMPix.o` to set everything
outside it to air. What must then be true:

* every table pixel reads air;
* every pixel inside the region keeps the value it had;
* and nothing outside the table that was already air changed value.

The phantom is computed here rather than read from disk: the fixture is images,
and images are not committed.
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

# The generator is the definition of the phantom; read its constants so this
# test cannot quietly measure a different picture.
generator = (root / 'tools/generate-ct-table-fixture.py').read_text()
for line in ('AIR, SOFT, BONE, TABLE = -1000, 40, 700, 200',
             'WIDTH = HEIGHT = 512',
             'CENTRE = (256, 216)',
             'RADII = (150, 110)',
             'BONE_THICKNESS = 8',
             'TABLE_ROWS = (400, 432)',
             'TABLE_COLUMNS = (96, 416)'):
    if line not in generator:
        failures.append('tools/generate-ct-table-fixture.py no longer says %r; the phantom below '
                        'would no longer be the one it writes' % line)

PROBE = r'''
#import <Foundation/Foundation.h>
#import "DCMPix.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>

enum { kBrush = 20 };   // tPlain in ToolMode

static const int kWidth = 512, kHeight = 512;
static const float kAir = -1000, kSoft = 40, kBone = 700, kTable = 200;
static const int kCentreX = 256, kCentreY = 216, kRadiusX = 150, kRadiusY = 110;
static const int kBoneThickness = 8;
static const int kTableRow0 = 400, kTableRow1 = 432;
static const int kTableColumn0 = 96, kTableColumn1 = 416;

static bool insideEllipse( int x, int y, int rx, int ry)
{
    double dx = (double)(x - kCentreX) / rx, dy = (double)(y - kCentreY) / ry;
    return dx * dx + dy * dy <= 1.0;
}

@interface ProbePix : DCMPix
- (void) preparePhantom;
@end
@implementation ProbePix
- (void) CheckLoad {}
- (float*) computefImage { return fImage; }
- (void) preparePhantom
{
    width = kWidth; height = kHeight; isRGB = NO; thickSlabVRActivated = NO;
    fImage = (float*) calloc( kWidth * kHeight, sizeof( float));
    baseAddr = (char*) calloc( kWidth * kHeight, 4);
    pixArray = [[NSArray arrayWithObject: [NSNull null]] retain];

    for( int y = 0; y < kHeight; y++)
        for( int x = 0; x < kWidth; x++)
        {
            float value = kAir;
            if( insideEllipse( x, y, kRadiusX, kRadiusY)) value = kBone;
            if( insideEllipse( x, y, kRadiusX - kBoneThickness, kRadiusY - kBoneThickness)) value = kSoft;
            if( y >= kTableRow0 && y < kTableRow1 && x >= kTableColumn0 && x < kTableColumn1)
                value = kTable;
            fImage[ y * kWidth + x] = value;
        }
}
@end

// fillROI asks a brush ROI only for its texture and its type.
@interface ROI : NSObject
@property (assign) long type;
@property (assign) unsigned char *textureBuffer;
@property (assign) long textureWidth, textureHeight;
@property (assign) long textureUpLeftCornerX, textureUpLeftCornerY;
@end
@implementation ROI
- (BOOL) isSpline { return NO; }
- (NSMutableArray*) splinePoints { return nil; }
@end

static int failures = 0;
static void check( bool ok, const char *what)
{
    if( !ok) { fprintf( stderr, "FAIL: %s\n", what); failures++; }
}

int main(){ @autoreleasepool {
    ProbePix *pix = [[ProbePix alloc] init];
    [pix preparePhantom];

    float *before = (float*) malloc( kWidth * kHeight * sizeof( float));
    memcpy( before, pix.fImage, kWidth * kHeight * sizeof( float));

    // A brush over the patient: the ellipse itself, in its bounding box. This
    // is what someone painting around the patient produces.
    const long boxX = kCentreX - kRadiusX, boxY = kCentreY - kRadiusY;
    const long boxW = 2 * kRadiusX + 1, boxH = 2 * kRadiusY + 1;
    unsigned char *texture = (unsigned char*) calloc( boxW * boxH, 1);
    long painted = 0;
    for( long y = 0; y < boxH; y++)
        for( long x = 0; x < boxW; x++)
            if( insideEllipse( (int)(boxX + x), (int)(boxY + y), kRadiusX, kRadiusY))
            { texture[ y * boxW + x] = 1; painted++; }

    ROI *roi = [[ROI alloc] init];
    roi.type = kBrush;
    roi.textureBuffer = texture;
    roi.textureWidth = boxW; roi.textureHeight = boxH;
    roi.textureUpLeftCornerX = boxX; roi.textureUpLeftCornerY = boxY;

    // The table sits below the patient, so it is outside the brush. Setting the
    // outside to air is the crop.
    [pix fillROI: (id) roi newVal: kAir minValue: -FLT_MAX maxValue: FLT_MAX
         outside: YES orientationStack: 2 stackNo: 0 restore: NO addition: NO];

    long tableLeft = 0, insideChanged = 0, outsideLeft = 0;
    for( int y = 0; y < kHeight; y++)
        for( int x = 0; x < kWidth; x++)
        {
            const long i = y * kWidth + x;
            const bool inBrush = insideEllipse( x, y, kRadiusX, kRadiusY);
            const bool inTable = (y >= kTableRow0 && y < kTableRow1
                                  && x >= kTableColumn0 && x < kTableColumn1);
            if( inTable && pix.fImage[ i] != kAir) tableLeft++;
            if( inBrush && pix.fImage[ i] != before[ i]) insideChanged++;
            if( !inBrush && pix.fImage[ i] != kAir) outsideLeft++;
        }

    char message[ 240];
    snprintf( message, sizeof message,
              "the table must be gone: %ld of %d pixels still read something other than air",
              tableLeft, (kTableRow1 - kTableRow0) * (kTableColumn1 - kTableColumn0));
    check( tableLeft == 0, message);

    snprintf( message, sizeof message,
              "the patient must be untouched: %ld of %ld pixels under the brush changed",
              insideChanged, painted);
    check( insideChanged == 0, message);

    snprintf( message, sizeof message,
              "everything outside the brush must read air: %ld pixels did not", outsideLeft);
    check( outsideLeft == 0, message);

    // And the crop has to have done something: the phantom must have had a
    // table to remove in the first place.
    long tableBefore = 0;
    for( int y = kTableRow0; y < kTableRow1; y++)
        for( int x = kTableColumn0; x < kTableColumn1; x++)
            if( before[ y * kWidth + x] == kTable) tableBefore++;
    snprintf( message, sizeof message, "the phantom had no table: %ld pixels at %+g HU",
              tableBefore, kTable);
    check( tableBefore == (kTableRow1 - kTableRow0) * (kTableColumn1 - kTableColumn0), message);

    if( failures) { fprintf( stderr, "FAIL: %d check%s\n", failures, failures == 1 ? "" : "s"); return 1; }
    printf( "removed %ld table pixels at %+g HU, left %ld patient pixels untouched\n",
            tableBefore, kTable, painted);
    return 0;
}}
'''

FRAMEWORKS = ['Foundation', 'AppKit', 'AVFoundation', 'CoreData', 'CoreMedia', 'CoreVideo']


def objectiveCStubs():
    listing = subprocess.run(['nm', '-u', str(obj)], capture_output=True, text=True, check=True).stdout
    names = sorted({m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)})
    sources = root / 'Horos/Sources'
    # HorosVRScissorBounds decides whether fillROI writes at all, so it is
    # compiled from its own source rather than stubbed.
    declared = [n for n in names
                if n not in ('ROI', 'HorosVRScissorBounds', 'HorosVRScissorPlan')
                and ((sources / (n + '.h')).is_file() or (sources / (n + '.m')).is_file()
                     or (sources / (n + '.mm')).is_file())]
    return ''.join('@interface %s : NSObject @end\n@implementation %s @end\n' % (n, n) for n in declared)


def link(directory, placeholders, scissor):
    assembly = ''.join('.globl %s\n%s: .quad 0\n' % (s, s) for s in sorted(placeholders))
    (directory / 'placeholders.s').write_text('.data\n' + assembly)
    command = ['xcrun', 'clang++', '-std=c++11', '-Wno-deprecated-declarations',
               '-I' + str(root / 'Horos/Sources'),
               str(directory / 'probe.mm'), str(directory / 'stubs.mm'),
               str(directory / 'placeholders.s'), str(obj), str(scissor),
               '-Wl,-undefined,dynamic_lookup', '-o', str(directory / 'probe')]
    for framework in FRAMEWORKS:
        command += ['-framework', framework]
    subprocess.run(command, check=True, capture_output=True)


if not failures:
    with tempfile.TemporaryDirectory(prefix='horos-ct-table-') as name:
        directory = Path(name)
        scissor = directory / 'VRScissorBounds.o'
        build = subprocess.run(
            ['xcrun', 'swiftc', '-emit-object', '-parse-as-library',
             str(root / 'Horos/Sources/VRScissorBounds.swift'),
             '-module-name', 'HorosProbe', '-o', str(scissor)],
            capture_output=True, text=True)
        if build.returncode:
            print('cannot compile VRScissorBounds.swift: %s' % build.stderr.strip(), file=sys.stderr)
            raise SystemExit(1)
        (directory / 'probe.mm').write_text(PROBE)
        (directory / 'stubs.mm').write_text('#import <Foundation/Foundation.h>\n' + objectiveCStubs())
        placeholders = set()
        for _ in range(200):
            link(directory, placeholders, scissor)
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
            failures.append('the crop did not remove the table')
        else:
            crop = run.stdout.strip()

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: synthetic CT table crop in a supported tool mode -- %s' % crop)
