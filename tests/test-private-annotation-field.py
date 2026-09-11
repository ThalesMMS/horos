#!/usr/bin/env python3
"""A custom annotation reads the element it names, private ones included.

Compiles the production field lookup against the built DCM framework and runs it
on a synthetic file. Needs that framework, which this repository does not carry.

Usage: python test-private-annotation-field.py PRODUCTS_DIR PRIVATE_FIXTURE
       PRODUCTS_DIR is build/Build/Products/Debug, holding DCM.framework
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

if len(sys.argv) < 3:
    print('skipped: needs the built DCM framework and a private-block fixture: '
          'PRODUCTS_DIR PRIVATE_FIXTURE', file=sys.stderr)
    raise SystemExit(2)

root = Path(__file__).resolve().parents[1]
products = Path(sys.argv[1]).resolve()
fixture = Path(sys.argv[2]).resolve()

source = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
start = source.index('- (NSString*) getDICOMFieldValueForGroup:')
lookup = source[start:source.index('\n}\n', start) + 2]

program = r'''
#import <Foundation/Foundation.h>
#import <DCM/DCM.h>

// The two formatters the lookup reaches for dates and times.
@interface BrowserController : NSObject
+ (NSString*) TimeWithSecondsFormat: (NSDate*) date;
+ (NSString*) DateTimeWithSecondsFormat: (NSDate*) date;
@end
@implementation BrowserController
+ (NSString*) TimeWithSecondsFormat: (NSDate*) date { return [date description]; }
+ (NSString*) DateTimeWithSecondsFormat: (NSDate*) date { return [date description]; }
@end

@interface NSUserDefaults (HorosDateFormatter)
+ (NSDateFormatter*) dateFormatter;
@end
@implementation NSUserDefaults (HorosDateFormatter)
+ (NSDateFormatter*) dateFormatter {
    NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
    formatter.dateStyle = NSDateFormatterShortStyle;
    return formatter;
}
@end

@interface PixProbe : NSObject
@end
@implementation PixProbe
LOOKUP
@end

static int failures = 0;
#define check(...) do{ if(!(__VA_ARGS__)){ NSLog(@"FAIL: %s", #__VA_ARGS__); failures++; } }while(0)

int main(int argc, char **argv) { @autoreleasepool {
    DCMObject *object = [DCMObject objectWithContentsOfFile:
                            [NSString stringWithUTF8String: argv[1]] decodingPixelData: NO];
    check(object != nil);

    PixProbe *probe = [PixProbe new];

    // The tag from the report, under its private creator.
    NSString *private = [probe getDICOMFieldValueForGroup: 0x0011 element: 0x1005 DCMLink: object];
    check([private isEqualToString: @"private annotation"]);

    // The same element under a different private group is a different value:
    // a lookup that ignores the group would return one for the other.
    NSString *other = [probe getDICOMFieldValueForGroup: 0x0013 element: 0x1005 DCMLink: object];
    check([other isEqualToString: @"other block"]);

    // A neighbouring element of the same block, to catch an off-by-one.
    NSString *number = [probe getDICOMFieldValueForGroup: 0x0011 element: 0x1006 DCMLink: object];
    check([number isEqualToString: @"42.5"]);

    // The private creator itself is readable, which is what names the block.
    NSString *creator = [probe getDICOMFieldValueForGroup: 0x0011 element: 0x0010 DCMLink: object];
    check([creator isEqualToString: @"HOROS PRIVATE TEST"]);

    // The patient name is the patient's name, not the word "PatientName".
    NSString *name = [probe getDICOMFieldValueForGroup: 0x0010 element: 0x0010 DCMLink: object];
    check(name != nil && [name rangeOfString: @"PRIVATE"].location != NSNotFound);
    check([name isEqualToString: @"PatientName"] == NO);

    // An element the file does not carry is absent, not another field's value.
    check([probe getDICOMFieldValueForGroup: 0x0011 element: 0x10ff DCMLink: object] == nil);
    check([probe getDICOMFieldValueForGroup: 0x0099 element: 0x0099 DCMLink: object] == nil);

    // No dictionary describes these tags, and asking for them does not raise.
    @try {
        for (int element = 0x1000; element < 0x1010; element++)
            [probe getDICOMFieldValueForGroup: 0x0011 element: element DCMLink: object];
    } @catch (NSException *e) {
        NSLog(@"FAIL: raised for a private tag: %@", e);
        failures++;
    }

    NSLog(@"%@", failures ? @"FAILURES" : @"lookup correct");
    return failures ? 1 : 0;
}}
'''.replace('LOOKUP', lookup)

# The placeholder that showed the word instead of the name, in both places.
assert 'value = @"PatientName"' not in source, (
    'a custom annotation on the patient name still shows the literal word')

with tempfile.TemporaryDirectory(prefix='horos-private-annotation-') as tmp:
    p = Path(tmp)
    # DCM.framework is installed as @executable_path/../Frameworks, which is
    # where it sits inside the application. Give the probe the same shape.
    (p / 'bin').mkdir()
    (p / 'Frameworks').symlink_to(products)
    (p / 'test.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fmodules',
                    '-F', str(products), '-framework', 'DCM', '-framework', 'Foundation',
                    str(p / 'test.m'), '-o', str(p / 'bin/test')], check=True)
    subprocess.run([str(p / 'bin/test'), str(fixture)], check=True)

print('PASS: private elements read under their own group, the private creator reads, '
      'absent tags are absent, and the patient name is the name')
