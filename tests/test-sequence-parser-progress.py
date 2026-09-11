#!/usr/bin/env python3
"""A malformed DICOM sequence ends the read instead of spinning.

The item loop is extracted from DCMObject.m and driven against data containers
that used to keep it going: one that never delimits, one that runs off the end,
and one that raises on every read. The previous loop is taken from the last
commit and run the same way, under a watchdog, to show what it did.
"""
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'DCM Framework/DCMObject.m').read_bytes().decode('latin1')

MARKER = '- (int) readNewSequenceAttribute:'
END = '- (DCMAttribute *) newAttributeForAttributeTag:'


def method(text):
    begin = text.index(MARKER)
    return text[begin:text.rindex('}', begin, text.index(END, begin)) + 1]


current = method(source)

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


old_source = revision_containing('DCM Framework/DCMObject.m', 'break; // Horos bug #210')
old = method(old_source) if old_source else None

code = r'''
#import <Foundation/Foundation.h>
#include <unistd.h>

static int failures;
#define check(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

#define DCMDEBUG 0

// Item and Sequence Delimitation Item, by the names the method looks up.
static NSDictionary *sharedTagForNameDictionary;

@interface DCMAttributeTag : NSObject
@property(retain) NSString *stringValue;
- (instancetype) initWithGroup:(int)group element:(int)element;
@end
@implementation DCMAttributeTag
@synthesize stringValue;
- (instancetype) initWithGroup:(int)group element:(int)element {
    if ((self = [super init]))
        stringValue = [[NSString stringWithFormat:@"%04X,%04X", group, element] retain];
    return self;
}
@end

@interface DCMCharacterSet : NSObject
- (NSString*) characterSet;
@end
@implementation DCMCharacterSet
- (NSString*) characterSet { return @"ISO_IR 100"; }
@end

// A stream the loop reads through. Each mode is a file the parser has to
// survive; `raises` counts how many reads have thrown, `reads` how many words
// have been handed out.
typedef enum { StreamNeverDelimits, StreamTruncated, StreamAlwaysRaises,
               StreamOneBadItemThenFine, StreamAlwaysBadTag } StreamMode;

@interface DCMDataContainer : NSObject
{
@public
    StreamMode mode;
    unsigned position_, length_;
    int words, raisesThrown, itemsHandedOut;
}
- (unsigned) position;
- (unsigned) length;
- (unsigned long) nextUnsignedLong;
- (unsigned short) nextUnsignedShort;
@end
@implementation DCMDataContainer
- (unsigned) position { return position_; }
- (unsigned) length { return length_; }
- (void) advance:(unsigned)bytes { position_ += bytes; }
- (unsigned short) nextUnsignedShort
{
    if (mode == StreamAlwaysRaises || (mode == StreamTruncated && position_ >= length_)) {
        raisesThrown++;
        [[NSException exceptionWithName:@"DCMInvalidLengthException"
                                 reason:@"Length of element exceeds length remaining in data."
                               userInfo:nil] raise];
    }
    [self advance: 2];
    int word = words++;
    // The first tag of the one-bad-item stream is not an item; everything after
    // it is. 0xFFFE,0xE000 is an Item, and no delimiter is ever handed out.
    if (mode == StreamOneBadItemThenFine && word < 2)
        return word == 0 ? 0x0008 : 0x0000;
    // Every tag readable and none of them an item: the reads advance, so only
    // counting the failures ends this one.
    if (mode == StreamAlwaysBadTag)
        return (word % 2) == 0 ? 0x0008 : 0x0000;
    return (word % 2) == 0 ? 0xFFFE : 0xE000;
}
- (unsigned long) nextUnsignedLong { [self advance: 4]; return 0; }
@end

@interface DCMAttribute : NSObject
@end
@implementation DCMAttribute
@end

@interface DCMSequenceAttribute : DCMAttribute
{
@public
    int items;
}
- (void) addItem:(id)object offset:(int)offset;
@end
@implementation DCMSequenceAttribute
- (void) addItem:(id)object offset:(int)offset { items++; }
@end

@interface DCMObject : NSObject
@property BOOL isSequence;
@property(retain) DCMCharacterSet *specificCharacterSet;
- (instancetype) initWithDataContainer:(DCMDataContainer*)data lengthToRead:(int)length
                            byteOffset:(int*)offset characterSet:(DCMCharacterSet*)set
                     decodingPixelData:(BOOL)decoding;
- (int) getGroup:(DCMDataContainer*)data;
- (int) getElement:(DCMDataContainer*)data;
@end

@implementation DCMObject
@synthesize isSequence, specificCharacterSet;

// Reading an item's dataset consumes its length and gets out of the way.
- (instancetype) initWithDataContainer:(DCMDataContainer*)data lengthToRead:(int)length
                            byteOffset:(int*)offset characterSet:(DCMCharacterSet*)set
                     decodingPixelData:(BOOL)decoding
{
    if ((self = [super init])) {
        data->itemsHandedOut++;
        if (length > 0 && length != 0xFFFFFFFF) { *offset += length; [data advance: length]; }
    }
    return self;
}
- (int) getGroup:(DCMDataContainer*)data { return [data nextUnsignedShort]; }
- (int) getElement:(DCMDataContainer*)data { return [data nextUnsignedShort]; }

METHOD
@end

// The loop must return; a watchdog turns "does not" into a failure with a name.
static void giveUp(int signal) { _exit(97); }

static int runSequence(StreamMode mode, int lengthToRead, int *offsetOut, DCMDataContainer **streamOut)
{
    DCMDataContainer *stream = [DCMDataContainer new];
    stream->mode = mode;
    // A real file is finite; that is what bounds an undelimited sequence.
    stream->length_ = (mode == StreamTruncated) ? 24 : 4096;
    DCMSequenceAttribute *attr = [DCMSequenceAttribute new];
    DCMObject *object = [DCMObject new];
    int offset = 0;
    int result = [object readNewSequenceAttribute: attr dicomData: stream byteOffset: &offset
                             lengthToRead: lengthToRead specificCharacterSet: [DCMCharacterSet new]];
    if (offsetOut) *offsetOut = offset;
    if (streamOut) *streamOut = stream;
    return result;
}

int main(int argc, const char **argv) { @autoreleasepool {
    sharedTagForNameDictionary = [@{@"Item": @"FFFE,E000",
                                    @"SequenceDelimitationItem": @"FFFE,E0DD"} retain];
    signal(SIGALRM, giveUp);
    alarm(10);

    BOOL previousBehaviour = (argc > 1 && strcmp(argv[1], "previous") == 0);

    // Undefined length, and the delimiter never arrives. This is the shape the
    // reports describe: repeated length and delimiter messages, forever.
    DCMDataContainer *stream = nil;
    int offset = 0;
    runSequence(StreamNeverDelimits, 0xFFFFFFFF, &offset, &stream);
    if (previousBehaviour) { printf("previous: returned from the undelimited sequence\n"); return 0; }
    check(offset > 0);

    // Reads that run off the end of the data.
    runSequence(StreamTruncated, 0xFFFFFFFF, &offset, &stream);
    check(stream->position_ <= stream->length_ + 8);

    // Every read raises. The loop caught them all and carried on.
    runSequence(StreamAlwaysRaises, 0xFFFFFFFF, &offset, &stream);
    check(stream->raisesThrown > 0);
    check(stream->raisesThrown <= 16);      // bounded, not one per word of the file

    // Tags that read cleanly and are never items: the loop advances, so it is
    // the run of failures that has to stop it, well before the data runs out.
    runSequence(StreamAlwaysBadTag, 0xFFFFFFFF, &offset, &stream);
    check(offset > 0);
    check(offset <= 8 * 9);                 // the failure limit is eight
    check(stream->position_ < stream->length_);

    // A defined length still ends where it says it does.
    int result = runSequence(StreamNeverDelimits, 64, &offset, &stream);
    check(result >= 64 - 8);

    // One bad item is still stepped over rather than ending the sequence: that
    // is the Philips workaround the commented out break was there for.
    runSequence(StreamOneBadItemThenFine, 64, &offset, &stream);
    check(stream->itemsHandedOut > 0);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("ok\n");
    return 0;
} }
'''

failures = []


def build(directory, name, body):
    path = Path(directory) / (name + '.m')
    path.write_text(code.replace('METHOD', body))
    binary = Path(directory) / name
    result = subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-unused-variable',
                             '-Wno-objc-method-access', str(path),
                             '-framework', 'Foundation', '-o', str(binary)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        return None
    return binary


with tempfile.TemporaryDirectory() as directory:
    binary = build(directory, 'current', current)
    if binary is None:
        failures.append('the current sequence reader does not compile')
        ran = 1
    else:
        ran = subprocess.run([str(binary)], timeout=60).returncode
        if ran == 97:
            failures.append('the current sequence reader did not return')

    if old is None:
        print('note: no revision in history still carries the previous sequence reader, '
              'so the loop it caused is not re-run here')
    else:
        binary = build(directory, 'previous', old)
        if binary is None:
            failures.append('the previous sequence reader does not compile')
        else:
            before = subprocess.run([str(binary), 'previous'], capture_output=True,
                                    text=True, timeout=60)
            if before.returncode == 97:
                print('the previous sequence reader never returned from an undelimited '
                      'sequence (stopped by the watchdog after 10 s)')
            else:
                failures.append('the previous sequence reader returned: %r' % before.stdout)

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if (failures or ran) else 0)
