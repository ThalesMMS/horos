#!/usr/bin/env python3
"""A missing or impossible BitsStored is read, not divided by.

Both halves are extracted from DCMPix.m: the part of the 0x0028 load that
decides bitsStored, and the sign extension in CheckLoad that used it as a
divisor. The previous sign extension is taken from the last commit and run in a
child process, so the crash it is being fixed for is demonstrated, not asserted.
"""
from pathlib import Path
import subprocess
import signal
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')


def region(text, start, end):
    begin = text.index(start)
    return text[begin:text.index(end, begin) + len(end)]


load = region(source,
              '    if( [dcmObject attributeValueWithName:@"BitsAllocated"])',
              'self->bitsStored = bitsAllocated;\n    }')
extend = region(source,
                '                if( fIsSigned && bitsAllocated != bitsStored) //We have to move the signing bit',
                'oImage =  (short*) tmpImage;\n                    }\n                }')

def revision_containing(path, marker):
    """The newest revision of `path` whose content still has `marker`.

    The comparison below is against the implementation this change replaced, so
    it has to be looked up rather than read from HEAD, which now holds the
    replacement. Returns None when history no longer carries it, in which case
    the comparison is skipped and the assertions about the current behaviour
    still run.
    """
    listed = subprocess.run(['git', 'log', '--format=%H', '--', path],
                            cwd=str(root), capture_output=True, text=True)
    for revision in listed.stdout.split():
        shown = subprocess.run(['git', 'show', '%s:%s' % (revision, path)],
                               cwd=str(root), capture_output=True)
        if shown.returncode == 0:
            content = shown.stdout.decode('latin1')
            if marker in content:
                return content
    return None


old_source = revision_containing('Horos/Sources/DCMPix.m', 'short div = pow( 2, shift);')
old_extend = old_load = None
if old_source:
    old_extend = region(old_source,
                        '                if( fIsSigned && bitsAllocated != bitsStored) //We have to move the signing bit',
                        'oImage =  (short*) tmpImage;\n                    }\n                }')
    old_load = region(old_source,
                      '    if( [dcmObject attributeValueWithName:@"BitsAllocated"])',
                      'else if (self->numberOfFrames <= 1)\n    {\n        self->bitsStored = __bitsStored;\n    }')

code = r'''
#import <Foundation/Foundation.h>
#include <math.h>

static int failures;
#define check(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

// The pixel object, reduced to the fields these two pieces touch.
@interface DCMPix : NSObject
{
@public
    short bitsAllocated, bitsStored;
    BOOL fIsSigned;
    long height, width, numberOfFrames;
    short *oImage;
}
@property(retain) NSString *srcFile;
@end

// A DICOM object that answers only the attributes the extracted load reads.
@interface StubObject : NSObject
{
@public
    NSDictionary *values;
}
- (NSString*) attributeValueWithName:(NSString*)name;
@end
@implementation StubObject
- (NSString*) attributeValueWithName:(NSString*)name { return values[name]; }
@end

// The same guard the load uses in DCMPix.m: a value is asked for a number only
// when it can answer for one. The stub only ever holds strings, so it always can.
static id horosNumberValue( StubObject *dcmObject, NSString *name, NSString *file)
{
    id value = [dcmObject attributeValueWithName: name];
    
    if( value == nil || [value respondsToSelector: @selector(floatValue)])
        return value;
    
    NSLog( @"---- %@: %@ is stored as %@, which is not a number; the attribute is ignored",
          [file lastPathComponent], name, NSStringFromClass( [value class]));
    
    return nil;
}

@implementation DCMPix
@synthesize srcFile;

- (void) loadFrom:(StubObject*)dcmObject
{
LOAD
}

// The sign extension, lifted out of CheckLoad with its surrounding conditions.
- (void) extend
{
EXTEND
}
@end

static DCMPix *pixWith(NSDictionary *attributes, BOOL isSigned)
{
    DCMPix *pix = [DCMPix new];
    pix.srcFile = @"/tmp/fixture.dcm";
    pix->fIsSigned = isSigned;
    StubObject *object = [StubObject new];
    object->values = attributes;
    [pix loadFrom: object];
    return pix;
}

// A one row image whose samples are twelve bit two's complement values sitting
// in the low bits of a sixteen bit field, which is what BitsStored 12 means.
static void fill(DCMPix *pix, const short *samples, int count)
{
    pix->height = 1;
    pix->width = count;
    pix->oImage = (short *) malloc(count * sizeof(short));
    memcpy(pix->oImage, samples, count * sizeof(short));
}

int main(int argc, const char **argv) { @autoreleasepool {
    BOOL previousBehaviour = (argc > 1 && strcmp(argv[1], "previous") == 0);
    const short stored12[] = { 0x0000, 0x0001, 0x07FF, 0x0800, 0x0FFF };
    const short expected12[] = { 0, 1, 2047, -2048, -1 };

    if (previousBehaviour) {
        // What the code before this change did with a missing BitsStored. The
        // divisor it computed is printed first, because that is the fact the
        // architecture does not change; whether dividing by it traps does.
        volatile double asDouble = pow(2, 16);
        printf("divisor %d\n", (int)(short) asDouble);
        fflush(stdout);
        DCMPix *pix = pixWith(@{@"BitsAllocated": @"16"}, YES);
        fill(pix, stored12, 5);
        [pix extend];
        printf("samples");
        for (int i = 0; i < 5; i++) printf(" %d", pix->oImage[i]);
        printf("\n");
        return 0;
    }

    // A file that says nothing about BitsStored is read at the allocated width.
    DCMPix *absent = pixWith(@{@"BitsAllocated": @"16"}, YES);
    check(absent->bitsStored == 16);
    fill(absent, stored12, 5);
    [absent extend];                       // must not divide by zero
    for (int i = 0; i < 5; i++)            // and must leave the samples alone
        check(absent->oImage[i] == stored12[i]);

    // Explicit zero, a negative value, and more bits than were allocated.
    check(pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"0"}, YES)->bitsStored == 16);
    check(pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"-3"}, YES)->bitsStored == 16);
    check(pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"32"}, YES)->bitsStored == 16);
    check(pixWith(@{@"BitsAllocated": @"8", @"BitsStored": @"16"}, NO)->bitsStored == 8);

    // A legal value is left exactly as the file states it.
    check(pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"12"}, YES)->bitsStored == 12);
    check(pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"16"}, YES)->bitsStored == 16);
    check(pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"1"}, YES)->bitsStored == 1);
    check(pixWith(@{@"BitsAllocated": @"8", @"BitsStored": @"8"}, NO)->bitsStored == 8);

    // Twelve significant bits still sign extend to the right numbers.
    DCMPix *twelve = pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"12"}, YES);
    fill(twelve, stored12, 5);
    [twelve extend];
    for (int i = 0; i < 5; i++)
        check(twelve->oImage[i] == expected12[i]);

    // Every legal width divides by something, including the extremes.
    for (int stored = 1; stored <= 16; stored++) {
        DCMPix *pix = pixWith(@{@"BitsAllocated": @"16",
                                @"BitsStored": [NSString stringWithFormat:@"%d", stored]}, YES);
        check(pix->bitsStored == stored);
        short samples[] = { 0x0001, 0x1234, -1 };
        fill(pix, samples, 3);
        [pix extend];                      // no crash at any width
    }

    // Unsigned data is not sign extended at all, whatever the widths say.
    DCMPix *unsignedPix = pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"12"}, NO);
    fill(unsignedPix, stored12, 5);
    [unsignedPix extend];
    for (int i = 0; i < 5; i++)
        check(unsignedPix->oImage[i] == stored12[i]);

    // A nested item carries no BitsStored; reading one must not wipe what the
    // enclosing object established. This is the other way it reached zero.
    DCMPix *nested = pixWith(@{@"BitsAllocated": @"16", @"BitsStored": @"12"}, YES);
    StubObject *item = [StubObject new];
    item->values = @{};                    // a pixel measures item, say
    [nested loadFrom: item];
    check(nested->bitsStored == 12);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("ok\n");
    return 0;
} }
'''


def build(directory, name, loading, extension):
    path = Path(directory) / (name + '.m')
    path.write_text(code.replace('LOAD', loading).replace('EXTEND', extension))
    binary = Path(directory) / name
    result = subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-unused-variable',
                             str(path), '-framework', 'Foundation', '-o', str(binary)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        return None
    return binary


failures = []
with tempfile.TemporaryDirectory() as directory:
    binary = build(directory, 'current', load, extend)
    if binary is None:
        failures.append('the current source does not compile')
        ran = 1
    else:
        ran = subprocess.run([str(binary)]).returncode

    # The crash this is fixing, reproduced against the code that had it.
    if old_extend is None or old_load is None:
        print('note: no revision in history still carries the previous BitsStored handling, '
              'so the crash it caused is not re-run here')
    else:
        binary = build(directory, 'previous', old_load, old_extend)
        if binary is None:
            failures.append('the previous source does not compile')
        else:
            ran_previous = subprocess.run([str(binary), 'previous'], capture_output=True, text=True)
            lines = ran_previous.stdout.split()
            # The divisor is 2^16 converted to a short: it does not fit, and the
            # conversion produces zero.
            if lines[:2] != ['divisor', '0']:
                failures.append('the previous divisor was %r, not zero' % (lines[1:2],))
            if ran_previous.returncode == -signal.SIGFPE:
                print('the previous sign extension divided by zero and died with SIGFPE')
            elif ran_previous.returncode == 0 and 'samples' in ran_previous.stdout:
                # Dividing by zero traps on x86_64 and silently yields zero on
                # arm64, so on this machine the samples are destroyed instead.
                samples = ran_previous.stdout.split('samples')[1].split()
                if samples == ['0'] * 5:
                    print('the previous sign extension divided by zero and blanked '
                          'every sample (arm64 sdiv does not trap; x86_64 idiv does)')
                else:
                    failures.append('the previous sign extension kept the samples: %r' % samples)
            else:
                failures.append('the previous sign extension behaved unexpectedly '
                                '(exit %d, output %r)' % (ran_previous.returncode, ran_previous.stdout))

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if (failures or ran) else 0)
