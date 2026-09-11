#!/usr/bin/env python3
"""Legacy Converted Enhanced CT, MR and PET are recognised as multi-frame images.

The real DCMAbstractSyntaxUID is compiled and asked, and the UIDs are checked
against DCMTK's dictionary in this checkout rather than against themselves.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

# The values DCMTK 3.6.7 defines, read out of its header: an independent source
# in this tree for what these UIDs are.
dcmtk = (root / 'DCMTK/dcmdata/include/dcmtk/dcmdata/dcuid.h').read_text(errors='replace')
expected = {}
for name in ('LegacyConvertedEnhancedCTImageStorage',
             'LegacyConvertedEnhancedMRImageStorage',
             'LegacyConvertedEnhancedPETImageStorage',
             'EnhancedCTImageStorage', 'EnhancedMRImageStorage', 'CTImageStorage'):
    match = re.search(r'#define UID_%s\s+"([\d.]+)"' % name, dcmtk)
    if not match:
        failures.append('DCMTK no longer defines UID_%s' % name)
    else:
        expected[name] = match.group(1)

code = r'''
#import <Foundation/Foundation.h>
#import "DCMAbstractSyntaxUID.h"

static int failures;
#define check(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static void recognised(NSString *uid, const char *label)
{
    if (![DCMAbstractSyntaxUID isImageStorage: uid]) { printf("FAIL %s is not image storage\n", label); failures++; }
    if (![DCMAbstractSyntaxUID isMultiframe: uid])   { printf("FAIL %s is not multiframe\n", label); failures++; }
}

int main(int argc, const char **argv) { @autoreleasepool {
    NSString *legacyCT  = [NSString stringWithUTF8String: argv[1]];
    NSString *legacyMR  = [NSString stringWithUTF8String: argv[2]];
    NSString *legacyPET = [NSString stringWithUTF8String: argv[3]];
    NSString *enhancedCT = [NSString stringWithUTF8String: argv[4]];
    NSString *enhancedMR = [NSString stringWithUTF8String: argv[5]];
    NSString *plainCT = [NSString stringWithUTF8String: argv[6]];

    // The three the issue is about. A file whose SOP Class is not recognised is
    // filtered out of the browser and the viewer before anything reads a pixel.
    recognised(legacyCT, "Legacy Converted Enhanced CT");
    recognised(legacyMR, "Legacy Converted Enhanced MR");
    recognised(legacyPET, "Legacy Converted Enhanced PET");

    // They are their own classes, not the ones they convert.
    check(![legacyCT isEqualToString: enhancedCT]);
    check(![legacyMR isEqualToString: enhancedMR]);

    // Nothing that already worked stopped working.
    recognised(enhancedCT, "Enhanced CT");
    recognised(enhancedMR, "Enhanced MR");
    check([DCMAbstractSyntaxUID isImageStorage: plainCT]);
    check(![DCMAbstractSyntaxUID isMultiframe: plainCT]);   // one frame per instance

    // And nothing became true for everything.
    check(![DCMAbstractSyntaxUID isImageStorage: @"1.2.840.10008.1.1"]);       // Verification
    check(![DCMAbstractSyntaxUID isMultiframe: @"1.2.840.10008.1.1"]);
    check(![DCMAbstractSyntaxUID isImageStorage: nil]);
    check(![DCMAbstractSyntaxUID isMultiframe: nil]);
    check(![DCMAbstractSyntaxUID isImageStorage: @""]);

    // They are not something else the browser routes elsewhere.
    check(![DCMAbstractSyntaxUID isStructuredReport: legacyCT]);
    check(![DCMAbstractSyntaxUID isPDF: legacyCT]);
    check(![DCMAbstractSyntaxUID isRadiotherapy: legacyMR]);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("ok\n");
    return 0;
} }
'''

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'main.m').write_text(code)
    build = subprocess.run(['xcrun', 'clang', '-fno-objc-arc',
                            '-I', str(root / 'DCM Framework'),
                            str(path / 'main.m'), str(root / 'DCM Framework/DCMAbstractSyntaxUID.m'),
                            '-framework', 'Foundation', '-framework', 'Cocoa',
                            '-o', str(path / 'test')], capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr)
        failures.append('DCMAbstractSyntaxUID.m does not compile')
        ran = 1
    else:
        ran = subprocess.run([str(path / 'test'),
                              expected.get('LegacyConvertedEnhancedCTImageStorage', ''),
                              expected.get('LegacyConvertedEnhancedMRImageStorage', ''),
                              expected.get('LegacyConvertedEnhancedPETImageStorage', ''),
                              expected.get('EnhancedCTImageStorage', ''),
                              expected.get('EnhancedMRImageStorage', ''),
                              expected.get('CTImageStorage', '')]).returncode

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if (failures or ran) else 0)
