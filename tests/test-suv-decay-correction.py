#!/usr/bin/env python3
"""Editing SUV values lands on the same corrected dose the load path produced.

The two production methods are extracted from DCMPix.m and compiled against a
stand-in object that holds only the SUV fields, so the arithmetic is exercised
without DICOM decoding. The SUV factor is the expression ViewerController uses.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')


def method(start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


methods = method('- (void) computeTotalDoseCorrected', '#ifndef OSIRIX_LIGHT')
methods += method('- (void) checkSUV', '#pragma mark -\n#pragma mark Database links')

# The factor both the conversion and the display path in ViewerController use.
viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
factor = viewer[viewer.index('else factorPET2SUV = ([pix patientsWeight]'):]
factor = factor[len('else '):factor.index(';') + 1]
factor = factor.replace('[pix patientsWeight]', 'self.patientsWeight')
factor = factor.replace('[pix radionuclideTotalDoseCorrected]', 'self.radionuclideTotalDoseCorrected')
factor = factor.replace('[pix decayFactor]', 'self.decayFactor')

code = r'''
#import <Foundation/Foundation.h>
#include <math.h>

static int failures;
#define check(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)
#define close_to(a, b) (fabs((a) - (b)) <= fabs(b) * 1e-5 + 1e-9)

@interface DCMPix : NSObject
{
    NSString *decayCorrection, *units;
    NSDate *acquisitionTime, *radiopharmaceuticalStartTime;
    float decayFactor, radionuclideTotalDose, radionuclideTotalDoseCorrected;
    float halflife, patientsWeight, philipsFactor, factorPET2SUV;
    BOOL hasSUV, isRGB;
}
@property(retain) NSString *decayCorrection, *units;
@property(retain) NSDate *acquisitionTime, *radiopharmaceuticalStartTime;
@property float decayFactor, radionuclideTotalDose, radionuclideTotalDoseCorrected;
@property float halflife, patientsWeight, philipsFactor;
@property BOOL hasSUV, isRGB;
- (float) suvFactor;
@end

@implementation DCMPix
@synthesize decayCorrection, units, acquisitionTime, radiopharmaceuticalStartTime;
@synthesize decayFactor, radionuclideTotalDose, radionuclideTotalDoseCorrected;
@synthesize halflife, patientsWeight, philipsFactor, hasSUV, isRGB;

METHODS

- (float) suvFactor
{
    float factorPET2SUV;
    FACTOR
    return factorPET2SUV;
}
@end

// A phantom: 10 mCi of F-18 injected an hour before a 70 kg acquisition.
static const float kDose = 370000000.f;      // Bq
static const float kHalflife = 6586.f;       // seconds, F-18
static const float kWeight = 70.f;
static const NSTimeInterval kDelay = 3600.;

static DCMPix *phantom(NSString *correction)
{
    DCMPix *pix = [DCMPix new];
    pix.units = @"BQML";
    pix.decayCorrection = correction;
    pix.decayFactor = 1.f;
    pix.halflife = kHalflife;
    pix.patientsWeight = kWeight;
    pix.radionuclideTotalDose = kDose;
    pix.radiopharmaceuticalStartTime = [NSDate dateWithTimeIntervalSinceReferenceDate: 0];
    pix.acquisitionTime = [NSDate dateWithTimeIntervalSinceReferenceDate: kDelay];
    return pix;
}

// What the load path does: correct the dose, then decide whether SUV applies.
static void load(DCMPix *pix)
{
    [pix computeTotalDoseCorrected];
    [pix checkSUV];
}

int main(void) { @autoreleasepool {
    float decayed = kDose * expf(-kDelay * logf(2.f) / kHalflife);

    // START is corrected to the injection time, so the exponential applies.
    DCMPix *start = phantom(@"START");
    load(start);
    check(start.hasSUV);
    check(close_to(start.radionuclideTotalDoseCorrected, decayed));

    // ADMIN and NONE are not, so the injected dose stands as measured.
    for (NSString *correction in @[@"ADMIN", @"NONE"]) {
        DCMPix *pix = phantom(correction);
        load(pix);
        check(pix.hasSUV);
        check(close_to(pix.radionuclideTotalDoseCorrected, kDose));
        check(pix.decayFactor == 1.f);
    }

    // The defect: the SUV panel calls computeTotalDoseCorrected on its own.
    // Editing must land where loading lands, for every correction mode.
    for (NSString *correction in @[@"START", @"ADMIN", @"NONE"]) {
        DCMPix *loaded = phantom(correction);
        load(loaded);

        DCMPix *edited = phantom(correction);
        load(edited);
        // The panel writes dose and injection time back, then recomputes.
        edited.radionuclideTotalDose = kDose;
        edited.radiopharmaceuticalStartTime = [NSDate dateWithTimeIntervalSinceReferenceDate: 0];
        [edited computeTotalDoseCorrected];

        check(close_to(edited.radionuclideTotalDoseCorrected, loaded.radionuclideTotalDoseCorrected));
        check(close_to(edited.suvFactor, loaded.suvFactor));
    }

    // Reopening the panel and committing the same values again must not decay
    // twice, which is what repeating the edit used to do on an ADMIN series.
    for (NSString *correction in @[@"START", @"ADMIN", @"NONE"]) {
        DCMPix *pix = phantom(correction);
        load(pix);
        float once = pix.radionuclideTotalDoseCorrected;
        for (int again = 0; again < 5; again++)
            [pix computeTotalDoseCorrected];
        check(close_to(pix.radionuclideTotalDoseCorrected, once));
    }

    // A new dose has to reach the corrected value, whatever the mode. Keeping
    // the previous number would price the SUV off a dose the user replaced.
    for (NSString *correction in @[@"START", @"ADMIN", @"NONE"]) {
        DCMPix *pix = phantom(correction);
        load(pix);
        float before = pix.radionuclideTotalDoseCorrected;
        pix.radionuclideTotalDose = kDose * 2.f;
        [pix computeTotalDoseCorrected];
        check(close_to(pix.radionuclideTotalDoseCorrected, before * 2.f));
    }

    // Editing the injection time only moves START.
    for (NSString *correction in @[@"START", @"ADMIN", @"NONE"]) {
        DCMPix *pix = phantom(correction);
        load(pix);
        float before = pix.radionuclideTotalDoseCorrected;
        pix.radiopharmaceuticalStartTime = [NSDate dateWithTimeIntervalSinceReferenceDate: -kHalflife];
        [pix computeTotalDoseCorrected];
        if ([correction isEqualToString: @"START"])
            check(close_to(pix.radionuclideTotalDoseCorrected, before * 0.5f));
        else
            check(close_to(pix.radionuclideTotalDoseCorrected, kDose));
    }

    // Values the panel can be handed that no correction can use. None of them
    // may leave a dose behind that came from the values they replaced.
    {
        DCMPix *pix = phantom(@"START");
        load(pix);
        pix.halflife = 0.f;
        [pix computeTotalDoseCorrected];
        check(pix.radionuclideTotalDoseCorrected == 0.f);
        [pix checkSUV];
        check(pix.hasSUV == NO);
    }
    {
        // Injection after acquisition: the panel rejects it, the file may carry it.
        DCMPix *pix = phantom(@"START");
        load(pix);
        pix.radiopharmaceuticalStartTime = [NSDate dateWithTimeIntervalSinceReferenceDate: kDelay + 60.];
        [pix computeTotalDoseCorrected];
        check(pix.radionuclideTotalDoseCorrected == 0.f);
    }
    {
        DCMPix *pix = phantom(@"ADMIN");
        load(pix);
        pix.radionuclideTotalDose = 0.f;
        [pix computeTotalDoseCorrected];
        check(pix.radionuclideTotalDoseCorrected == 0.f);
        [pix checkSUV];
        check(pix.hasSUV == NO);
    }
    {
        // Missing times are fine for ADMIN and fatal for START.
        DCMPix *admin = phantom(@"ADMIN");
        admin.acquisitionTime = nil;
        admin.radiopharmaceuticalStartTime = nil;
        load(admin);
        check(admin.hasSUV);
        check(close_to(admin.radionuclideTotalDoseCorrected, kDose));

        DCMPix *start = phantom(@"START");
        start.acquisitionTime = nil;
        start.radiopharmaceuticalStartTime = nil;
        load(start);
        check(start.hasSUV == NO);
        check(start.radionuclideTotalDoseCorrected == 0.f);
    }
    {
        // An unknown DecayCorrection stays out of SUV entirely.
        DCMPix *pix = phantom(@"OTHER");
        load(pix);
        check(pix.hasSUV == NO);
    }

    // The SUV of a 1 Bq/cc voxel, checked against the definition by hand.
    DCMPix *admin = phantom(@"ADMIN");
    load(admin);
    check(close_to(admin.suvFactor, kWeight * 1000.f / kDose));
    DCMPix *startPix = phantom(@"START");
    load(startPix);
    check(close_to(startPix.suvFactor, kWeight * 1000.f / decayed));
    // An hour is a bit over half an F-18 half-life, so START reads higher.
    check(startPix.suvFactor > admin.suvFactor);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("ok\n");
    return 0;
} }
'''

code = code.replace('METHODS', methods).replace('FACTOR', factor)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'main.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wno-unused-variable',
                    str(path / 'main.m'), '-framework', 'Foundation',
                    '-o', str(path / 'test')], check=True)
    sys.exit(subprocess.run([str(path / 'test')]).returncode)
