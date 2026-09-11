#!/usr/bin/env python3
"""Both ultrasound region unit strings are decided, whatever the tags say.

A ROI inside an ultrasound region labels its position and length with a unit per
axis, read from Physical Units X Direction (0018,6024) and Y Direction
(0018,6026). The two are independent, but the code chose them in one
if/else-if chain:

    if (X out of range)      unitsX = "unknown";   // unitsY never assigned
    else if (Y out of range) unitsY = "unknown";   // unitsX never assigned
    else                     both = table[...];

so an out-of-range value on either axis left the *other* string uninitialised,
and the uninitialised pointer was then formatted into the label and compared
with isEqualToString:. Undefined behaviour in a measurement label.

This compiles the real selection for every value either axis can carry,
including the out-of-range ones, and requires both strings to come out decided.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
source = (root / 'Horos/Sources/ROI.m').read_bytes().decode('latin1')

# --- neither string may be left to a later branch ----------------------------
declarations = re.findall(r'NSString \* units([XY])\s*(=|;)', source)
if not declarations:
    print('FAIL: the unit strings are gone from ROI.m', file=sys.stderr)
    sys.exit(1)
for axis, form in declarations:
    if form != '=':
        failures.append('units%s is declared without a value, so a branch can leave it unset'
                        % axis)
# Both sites, both axes.
if len(declarations) != 4:
    failures.append('expected four unit declarations (two sites, two axes), found %d'
                    % len(declarations))

# --- the selection itself, compiled and run ----------------------------------
picked = re.search(
    r'NSString \* unitsX = \(\(physicalUnitsXDirection.*?physicalUnitsXDirection\];\s*'
    r'NSString \* unitsY = \(\(physicalUnitsYDirection.*?physicalUnitsYDirection\];',
    source, re.S)
if not picked:
    failures.append('the per-axis selection is no longer in the shape this test can extract')
else:
    body = picked.group(0)
    table = re.search(r'NSArray \* physicalUnitsXYDirection = [^;]+;', source, re.S).group(0)
    code = '''
#import <Foundation/Foundation.h>
#define NSLocalizedString(k, c) (k)
int main(void) { @autoreleasepool {
    int bad = 0;
    for (int x = -2; x <= 14; ++x) {
        for (int y = -2; y <= 14; ++y) {
            int physicalUnitsXDirection = x, physicalUnitsYDirection = y;
            TABLE
            SELECTION
            if (unitsX == nil || unitsY == nil) {
                printf("FAIL: nil unit at x=%d y=%d\\n", x, y); bad = 1; continue;
            }
            // A value outside 0..12 has no entry in the table, and only that
            // axis may fall back.
            BOOL xKnown = (x >= 0 && x <= 12), yKnown = (y >= 0 && y <= 12);
            if (xKnown && [unitsX isEqualToString: @"unknown"] && ![[physicalUnitsXYDirection objectAtIndex: x] isEqualToString: @"unknown"]) {
                printf("FAIL: x=%d is in range but unitsX is unknown\\n", x); bad = 1;
            }
            if (!xKnown && ![unitsX isEqualToString: @"unknown"]) {
                printf("FAIL: x=%d is out of range but unitsX is %s\\n", x, [unitsX UTF8String]); bad = 1;
            }
            if (yKnown && [unitsY isEqualToString: @"unknown"] && ![[physicalUnitsXYDirection objectAtIndex: y] isEqualToString: @"unknown"]) {
                printf("FAIL: y=%d is in range but unitsY is unknown\\n", y); bad = 1;
            }
            if (!yKnown && ![unitsY isEqualToString: @"unknown"]) {
                printf("FAIL: y=%d is out of range but unitsY is %s\\n", y, [unitsY UTF8String]); bad = 1;
            }
        }
    }
    if (!bad) puts("PASS: every axis pair decides both unit strings");
    return bad;
}}
'''.replace('TABLE', table).replace('SELECTION', body)
    with tempfile.TemporaryDirectory(prefix='horos-us-units-') as tmp:
        path = Path(tmp)
        (path / 'main.m').write_text(code)
        build = subprocess.run(
            ['xcrun', 'clang', '-fobjc-arc', '-Werror=uninitialized',
             '-Werror=sometimes-uninitialized', '-framework', 'Foundation',
             str(path / 'main.m'), '-o', str(path / 'test')],
            capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('the extracted selection does not compile cleanly:\n%s'
                            % build.stderr[-1200:])
        else:
            run = subprocess.run([str(path / 'test')], capture_output=True, text=True)
            sys.stdout.write(run.stdout)
            if run.returncode != 0:
                failures.append('the selection left a unit undecided')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: ultrasound region units are decided per axis at both sites')
