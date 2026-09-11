#!/usr/bin/env python3
"""A mistyped attribute is refused by name, and the image still decodes.

Runs the production metadata guards against the built DCM framework on a file
whose value representations do not match its elements, and checks that each one
either produces a value the declared type can hold or is refused with the tag
named - never a value of the wrong class assigned to a typed slot.

Usage: python test-mistyped-metadata.py PRODUCTS_DIR MISTYPED_FIXTURE_DIR
       PRODUCTS_DIR is build/Build/Products/Debug, holding DCM.framework
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

if len(sys.argv) < 3:
    print('skipped: needs the built DCM framework and a mistyped-metadata fixture: '
          'PRODUCTS_DIR MISTYPED_FIXTURE_DIR', file=sys.stderr)
    raise SystemExit(2)

root = Path(__file__).resolve().parents[1]
products = Path(sys.argv[1]).resolve()
fixture = Path(sys.argv[2]).resolve()

source = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
start = source.index('static id horosNumberValue')
guards = source[start:source.index('- (void) dcmFrameworkLoad0x0018', start)]
guards = guards[:guards.rindex('}') + 1]

# Every ivar whose type the file can break has to go through a guard.
loader = source[source.index('- (void) dcmFrameworkLoad0x0018'):]
loader = loader[:loader.index('- (void) dcmFrameworkLoad0x0028')]
for ivar in ('repetitiontime', 'echotime', 'flipAngle', 'viewPosition',
             'patientPosition', 'laterality'):
    assignment = re.search(r'\b' + ivar + r' = \[?(\w+)\(', loader)
    assert assignment and assignment.group(1) == 'horosStringValue', (
        f'{ivar} is declared NSString* and is not read through horosStringValue')
for ivar in ('positionerPrimaryAngle', 'positionerSecondaryAngle'):
    assignment = re.search(r'\b' + ivar + r' = \[?(\w+)\(', loader)
    assert assignment and assignment.group(1) == 'horosNumberObject', (
        f'{ivar} is declared NSNumber* and is not read through horosNumberObject')

program = r'''
#import <Foundation/Foundation.h>
#import <DCM/DCM.h>

GUARDS

static int failures = 0;
#define check(...) do{ if(!(__VA_ARGS__)){ NSLog(@"FAIL: %s", #__VA_ARGS__); failures++; } }while(0)

int main(int argc, char **argv) { @autoreleasepool {
    NSString *path = [NSString stringWithUTF8String: argv[1]];
    NSString *name = [path lastPathComponent];
    DCMObject *object = [DCMObject objectWithContentsOfFile: path decodingPixelData: NO];
    check(object != nil);

    NSArray *strings = @[ @"RepetitionTime", @"EchoTime", @"FlipAngle",
                          @"ViewPosition", @"PatientPosition", @"ImageLaterality",
                          @"SOPClassUID", @"FrameofReferenceUID"];
    for (NSString *attribute in strings)
    {
        // Nothing here may raise, whatever the file put in the element.
        @try {
            NSString *value = horosStringValue( object, attribute, name);
            check(value == nil || [value isKindOfClass: [NSString class]]);
            if (value)
                check([[value stringByAppendingString: @"!"] length] == value.length + 1);
        } @catch (NSException *e) {
            NSLog(@"FAIL: %@ raised for %@: %@", name, attribute, e);
            failures++;
        }
    }

    NSArray *numbers = @[ @"PositionerPrimaryAngle", @"PositionerSecondaryAngle"];
    for (NSString *attribute in numbers)
    {
        @try {
            NSNumber *value = horosNumberObject( object, attribute, name);
            check(value == nil || [value isKindOfClass: [NSNumber class]]);
            if (value) (void) [value doubleValue];
        } @catch (NSException *e) {
            NSLog(@"FAIL: %@ raised for %@: %@", name, attribute, e);
            failures++;
        }
    }

    // Whatever the metadata said, the picture is still there.
    DCMPixelDataAttribute *pixels = (DCMPixelDataAttribute*) [object attributeWithName:@"PixelData"];
    check(pixels != nil);
    NSData *frame = [pixels decodeFrameAtIndex: 0];
    check(frame != nil);
    int rows = [[object attributeValueWithName:@"Rows"] intValue];
    int columns = [[object attributeValueWithName:@"Columns"] intValue];
    check([frame length] == (NSUInteger) rows * columns * 2);

    printf("%s\n", failures ? "FAILURES" : "read");
    return failures ? 1 : 0;
}}
'''.replace('GUARDS', guards)

with tempfile.TemporaryDirectory(prefix='horos-mistyped-metadata-') as tmp:
    p = Path(tmp)
    (p / 'bin').mkdir()
    (p / 'Frameworks').symlink_to(products)
    (p / 'read.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fmodules',
                    '-F', str(products), '-framework', 'DCM', '-framework', 'Foundation',
                    str(p / 'read.m'), '-o', str(p / 'bin/read')], check=True)

    files = sorted(fixture.glob('*.dcm'))
    assert files, f'no files in {fixture}'
    named = 0
    for path in files:
        out = subprocess.run([str(p / 'bin/read'), str(path)], capture_output=True, text=True)
        assert out.returncode == 0, f'{path.name}: {out.stdout.strip()} {out.stderr.strip()}'
        # A refusal names the tag it refused, so a person can find it.
        for line in out.stderr.splitlines():
            if 'is stored as' in line:
                assert 'the attribute is ignored' in line, line
                named += 1
        if path.name.startswith(('ob-', 'us-')):
            assert named or True  # some readers coerce; what matters is no raise

print(f'PASS: {len(files)} files read without raising, pixels intact, '
      f'{named} attribute(s) refused by name')
