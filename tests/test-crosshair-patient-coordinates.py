#!/usr/bin/env python3
"""#373/A295: the crosshair travels as patient coordinates, and the slab ends agree.

A295 asks for a crosshair placed by patient coordinates between viewers. Two
things have to hold for that.

**The point has to be patient coordinates.** `-[DCMView sync3DPosition]` converts
the mouse position to DICOM coordinates and sends them; the receiver finds the
nearest plane and converts back into its own slice. Those two conversions are
`-[DCMPix convertPixX:pixY:toDICOMCoords:pixelCenter:]` and
`-[DCMPix convertDICOMCoords:toSliceCoords:]`, and this links the application's
own `DCMPix.o` to put a point through both across series that do not share an
orientation.

**Both ends of a thick slab have to be the right ones.** The sender ships the
current slice and the far end of the slab, so the receiver can draw the band
rather than one line. `-syncMessage:` honoured `flippedData` when picking that
far end and `-sync3DPosition` — the one that carries the crosshair — did not, so
a reversed series sent the band from the wrong side. `HorosThickSlabRange` is now
the single answer, and this requires both senders to ask it.
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

# -------------------------------------------------------------- the slab rule

rule = root / 'Horos/Sources/ThickSlabRange.swift'
if not rule.is_file():
    failures.append('Horos/Sources/ThickSlabRange.swift is missing')
else:
    driver = r'''
import Foundation

@main struct Check {
    static func main() {
        typealias R = ThickSlabRange
        // No slab: nothing to send as a second end.
        precondition(R.farEndIndex(currentIndex: 4, stack: 1, count: 16, flippedData: false) == -1)
        precondition(R.farEndIndex(currentIndex: 4, stack: 0, count: 16, flippedData: false) == -1)
        precondition(R.farEndIndex(currentIndex: 0, stack: 4, count: 0, flippedData: false) == -1)

        // The slab runs forward, or backward when the series is reversed. This
        // is the difference -sync3DPosition did not make.
        precondition(R.farEndIndex(currentIndex: 4, stack: 5, count: 16, flippedData: false) == 8)
        precondition(R.farEndIndex(currentIndex: 8, stack: 5, count: 16, flippedData: true) == 4)
        precondition(R.farEndIndex(currentIndex: 4, stack: 5, count: 16, flippedData: false)
                     != R.farEndIndex(currentIndex: 4, stack: 5, count: 16, flippedData: true))

        // A slab may reach past either end; the index still has to be one.
        precondition(R.farEndIndex(currentIndex: 14, stack: 8, count: 16, flippedData: false) == 15)
        precondition(R.farEndIndex(currentIndex: 1, stack: 8, count: 16, flippedData: true) == 0)
        precondition(R.farEndIndex(currentIndex: 0, stack: 2, count: 1, flippedData: false) == 0)
        print("rule ok")
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='horos-thick-slab-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(rule),
                                str(path / 'Check.swift'), '-o', str(path / 'check')],
                               capture_output=True, text=True)
        if build.returncode:
            failures.append('the slab rule does not compile: %s'
                            % build.stderr.strip().splitlines()[-3:])
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            if run.returncode:
                failures.append('the slab rule does not answer: %s' % run.stderr.strip())

# ----------------------------------------------------- both senders ask for it

view = (root / 'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
for name, pattern in (('sync3DPosition', r'- \(void\) sync3DPosition\s*\{(.*?)\n\}'),
                      ('syncMessage:', r'- \(NSDictionary\*\) syncMessage:\(short\) inc\s*\{(.*?)\n\}')):
    body = re.search(pattern, view, re.S)
    if not body:
        failures.append('-[DCMView %s] is gone' % name)
        continue
    if 'HorosThickSlabRange' not in body.group(1):
        failures.append('%s must ask HorosThickSlabRange for the far end of the slab' % name)
    if re.search(r'stack\s*-\s*1\)', body.group(1)):
        failures.append('%s still computes the slab end itself' % name)
    if 'DCMPix2' not in body.group(1):
        failures.append('%s no longer sends the far end at all' % name)

# The receiver has to consume patient coordinates, and only inside the same-world
# guard -- otherwise the crosshair would cross frames of reference.
receiver = re.search(r'-\(void\) sync:\(NSNotification\*\)note\s*\{(.*?)\n\}\n\n', view, re.S)
if not receiver:
    failures.append('-[DCMView sync:] is gone')
else:
    text = receiver.group(1)
    for key in ('point3DX', 'point3DY', 'point3DZ'):
        if key not in text:
            failures.append('sync: no longer reads %s' % key)
    if 'findPlaneAndPoint' not in text:
        failures.append('sync: no longer finds the plane for the patient point')
    if 'convertDICOMCoords:' not in text:
        failures.append('sync: no longer converts the patient point into its own slice')
    world = text.find('same3DReferenceWorld || registeredViewer')
    point = text.find('if( point3D)')
    if world < 0 or point < 0 or not world < point:
        failures.append('the patient-coordinate crosshair must stay inside the same-world guard')

sender = re.search(r'- \(void\) sync3DPosition\s*\{(.*?)\n\}', view, re.S)
if sender and 'convertPixX:' not in sender.group(1):
    failures.append('sync3DPosition no longer converts the mouse position to patient coordinates')

# -convertDICOMCoords:toSliceCoords: answers in millimetres; the drawing turns
# that into pixels. Both halves have to stay, or the crosshair moves by the
# pixel spacing without anything looking wrong.
if not re.search(r'slicePoint3D\[\s*0\]\s*/\s*self\.curDCM\.pixelSpacingX', view):
    failures.append('the crosshair is no longer divided by pixelSpacingX before being drawn')
if not re.search(r'slicePoint3D\[\s*1\]\s*/\s*self\.curDCM\.pixelSpacingY', view):
    failures.append('the crosshair is no longer divided by pixelSpacingY before being drawn')

project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
if 'ThickSlabRange.swift in Sources' not in project:
    failures.append('ThickSlabRange.swift is not compiled into the Horos target')

# ------------------------------------------------------ the coordinate round trip

PROBE = r'''
#import <Foundation/Foundation.h>
#import "DCMPix.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>

@interface ProbePix : DCMPix
- (void) prepareOrientation:(const double*)o origin:(const double*)p;
@end
@implementation ProbePix
- (void) CheckLoad {}
- (float*) computefImage { return fImage; }
- (void) prepareOrientation:(const double*)o origin:(const double*)p
{
    width = 64; height = 64; isRGB = NO;
    pixelSpacingX = pixelSpacingY = 2.0;      // 2 mm pixels, so a wrong factor shows
    for( int i = 0; i < 6; i++) orientation[ i] = o[ i];
    // The third vector is the slice normal; DCMPix fills it from the first two.
    orientation[ 6] = orientation[ 1]*orientation[ 5] - orientation[ 2]*orientation[ 4];
    orientation[ 7] = orientation[ 2]*orientation[ 3] - orientation[ 0]*orientation[ 5];
    orientation[ 8] = orientation[ 0]*orientation[ 4] - orientation[ 1]*orientation[ 3];
    originX = p[ 0]; originY = p[ 1]; originZ = p[ 2];
}
@end

static int failures = 0;
static void check( bool ok, const char *what)
{
    if( !ok) { fprintf( stderr, "FAIL: %s\n", what); failures++; }
}

int main(){ @autoreleasepool {
    // Axial: rows along +y, columns along +x, plane at z = 30.
    const double axialOrientation[ 6] = {1,0,0, 0,1,0};
    const double axialOrigin[ 3] = {-64, -64, 30};
    // Coronal: rows along +z, columns along +x, plane at y = -10.
    const double coronalOrientation[ 6] = {1,0,0, 0,0,1};
    const double coronalOrigin[ 3] = {-64, -10, -64};

    ProbePix *axial = [[ProbePix alloc] init];
    [axial prepareOrientation: axialOrientation origin: axialOrigin];
    ProbePix *coronal = [[ProbePix alloc] init];
    [coronal prepareOrientation: coronalOrientation origin: coronalOrigin];

    // A pixel picked in the axial view, as -sync3DPosition does.
    const float pickX = 40, pickY = 12;
    float patient[ 3];
    [axial convertPixX: pickX pixY: pickY toDICOMCoords: patient pixelCenter: YES];

    char message[ 256];
    // 2 mm pixels from (-64, -64, 30), pixel centres: x = -64 + (40 - 0.5)*2,
    // y = -64 + (12 - 0.5)*2, and the slice keeps its own z.
    snprintf( message, sizeof message, "the picked point in patient coordinates is (%g, %g, %g)",
              patient[ 0], patient[ 1], patient[ 2]);
    check( fabs( patient[ 0] - 15) < 0.001 && fabs( patient[ 1] + 41) < 0.001
           && fabs( patient[ 2] - 30) < 0.001, message);

    // -convertDICOMCoords:toSliceCoords: answers in MILLIMETRES along the row
    // and column vectors, not in pixels. The drawing divides by the pixel
    // spacing, which is what makes the trip lossless -- check that it is.
    float back[ 3];
    [axial convertDICOMCoords: patient toSliceCoords: back];
    const float backX = back[ 0] / axial.pixelSpacingX, backY = back[ 1] / axial.pixelSpacingY;
    snprintf( message, sizeof message,
              "the axial round trip gave %g mm, %g mm = pixel (%g, %g), from (%g, %g)",
              back[ 0], back[ 1], backX, backY, pickX, pickY);
    check( fabs( backX - pickX) < 0.001 && fabs( backY - pickY) < 0.001, message);
    snprintf( message, sizeof message,
              "slice coordinates must be millimetres, not pixels: got %g for pixel %g",
              back[ 0], pickX);
    check( fabs( back[ 0] - pickX) > 0.001, message);

    // The same patient point in the coronal view: x = 15 is column 40, z = 30
    // is row 47.5, and the point is 31 mm off that coronal plane in y.
    float other[ 3];
    [coronal convertDICOMCoords: patient toSliceCoords: other];
    const float otherX = other[ 0] / coronal.pixelSpacingX, otherY = other[ 1] / coronal.pixelSpacingY;
    snprintf( message, sizeof message,
              "the coronal view places the point at pixel (%g, %g), %g mm off plane; expected (40, 47.5) and 31",
              otherX, otherY, fabs( other[ 2]));
    check( fabs( otherX - 40) < 0.001 && fabs( otherY - 47.5) < 0.001
           && fabs( fabs( other[ 2]) - 31) < 0.001, message);

    // The off-plane distance is what -findPlaneAndPoint: uses to refuse a point
    // that is nowhere near this series; it must not come out as zero here.
    check( fabs( other[ 2]) > 0.001, "the coronal plane is not the axial plane; the distance must say so");

    if( failures) { fprintf( stderr, "FAIL: %d check%s\n", failures, failures == 1 ? "" : "s"); return 1; }
    printf( "pixel (%g, %g) -> patient (%g, %g, %g) -> coronal pixel (%g, %g), %g mm off plane",
            pickX, pickY, patient[0], patient[1], patient[2], otherX, otherY, fabs( other[2]));
    return 0;
}}
'''

FRAMEWORKS = ['Foundation', 'AppKit', 'AVFoundation', 'CoreData', 'CoreMedia', 'CoreVideo']


def objectiveCStubs():
    listing = subprocess.run(['nm', '-u', str(obj)], capture_output=True, text=True, check=True).stdout
    names = sorted({m.group(1) for m in re.finditer(r'_OBJC_CLASS_\$_(\w+)', listing)})
    sources = root / 'Horos/Sources'
    declared = [n for n in names
                if n != 'ROI' and ((sources / (n + '.h')).is_file() or (sources / (n + '.m')).is_file()
                                   or (sources / (n + '.mm')).is_file())]
    return ('@interface ROI : NSObject @end\n@implementation ROI @end\n'
            + ''.join('@interface %s : NSObject @end\n@implementation %s @end\n' % (n, n)
                      for n in declared))


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


roundTrip = ''
if not failures:
    with tempfile.TemporaryDirectory(prefix='horos-crosshair-') as name:
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
            failures.append('the patient-coordinate round trip does not land where the geometry says')
        else:
            roundTrip = run.stdout.strip()

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: %s; both senders agree on the far end of a thick slab' % roundTrip)
