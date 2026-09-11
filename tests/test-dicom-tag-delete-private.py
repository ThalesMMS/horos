#!/usr/bin/env python3
"""Removing a tag removes it, emptying keeps it, and a private value persists.

The three production pieces — the entry reader, the private element writer and
the dispatch loop between them — are extracted from XMLControllerDCMTKCategory.mm
and run against the project's own GDCM on a synthetic file written here.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/XMLControllerDCMTKCategory.mm').read_bytes().decode('latin1')

gdcm = root / 'build/Build/Intermediates.noindex/Horos.build/Debug/GDCM.build/Install'
if not (gdcm / 'lib').is_dir():
    print('skip: the project GDCM is not built at %s' % gdcm)
    sys.exit(0)


def between(start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


extraction = between('typedef struct\n{\n    unsigned short group;', '@implementation XMLController')
loop = between('for( std::vector<HorosTagEdit>::const_iterator it2', 'if (!success)')

# ---------------------------------------------------------------- the fixture
#
# Explicit VR little endian, written here so the private block is exactly what
# the test needs: a creator at (0009,0010) owning (0009,1001) as a text element
# and (0009,1002) as a binary one, plus an optional public tag to remove.

def element(group, number, vr, payload):
    if len(payload) % 2:
        payload += b'\x00' if vr == b'UI' else b' '
    if vr in (b'OB', b'OW', b'OF', b'SQ', b'UT', b'UN'):
        return struct.pack('<HH2sHI', group, number, vr, 0, len(payload)) + payload
    return struct.pack('<HH2sH', group, number, vr, len(payload)) + payload


CLASS_UID = b'1.2.840.10008.5.1.4.1.1.7'          # Secondary Capture
INSTANCE_UID = b'1.2.826.0.1.3680043.8.498.10001'
EXPLICIT_LITTLE = b'1.2.840.10008.1.2.1'

meta = (element(0x0002, 0x0002, b'UI', CLASS_UID)
        + element(0x0002, 0x0003, b'UI', INSTANCE_UID)
        + element(0x0002, 0x0010, b'UI', EXPLICIT_LITTLE)
        + element(0x0002, 0x0012, b'UI', b'1.2.826.0.1.3680043.8.498.1'))
meta = element(0x0002, 0x0000, b'UL', struct.pack('<I', len(meta))) + meta

dataset = (element(0x0008, 0x0016, b'UI', CLASS_UID)
           + element(0x0008, 0x0018, b'UI', INSTANCE_UID)
           + element(0x0008, 0x0060, b'CS', b'OT')
           + element(0x0008, 0x1030, b'LO', b'Tag editor fixture')      # optional
           + element(0x0010, 0x0010, b'PN', b'FIXTURE^TAG')
           + element(0x0010, 0x0020, b'LO', b'TAG-0001')
           + element(0x0009, 0x0010, b'LO', b'HOROS TEST CREATOR')      # private creator
           + element(0x0009, 0x1001, b'LO', b'original private')        # text
           + element(0x0009, 0x1002, b'OB', b'\x01\x02\x03\x04')        # binary
           + element(0x0020, 0x000D, b'UI', b'1.2.826.0.1.3680043.8.498.2')
           + element(0x0020, 0x000E, b'UI', b'1.2.826.0.1.3680043.8.498.3')
           + element(0x0020, 0x0013, b'IS', b'1'))

fixture = b'\x00' * 128 + b'DICM' + meta + dataset

# ---------------------------------------------------------------- the harness
code = r'''
#import <Foundation/Foundation.h>
#include <sstream>
#include <string>
#include <vector>
#include <GDCM/gdcmReader.h>
#include <GDCM/gdcmWriter.h>
#include <GDCM/gdcmAnonymizer.h>

static int failures;
#define check(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

// Stands in for the tag object the editor builds from the row's path.
@interface DCMAttributeTag : NSObject
@property int group, element;
+ (instancetype) group:(int)g element:(int)e;
@end
@implementation DCMAttributeTag
@synthesize group, element;
+ (instancetype) group:(int)g element:(int)e {
    DCMAttributeTag *tag = [DCMAttributeTag new];
    tag.group = g; tag.element = e;
    return tag;
}
@end

EXTRACTION

// The write half of +modifyDicom:dicomFiles:reasons:, with the extracted loop.
static BOOL applyEdits(NSString *path, NSArray *tagAndValues, NSArray **reasons, NSUInteger *rejectedOut)
{
    NSMutableArray *refusals = [NSMutableArray array];
    gdcm::Reader reader;
    reader.SetFileName([path fileSystemRepresentation]);
    if (!reader.Read()) { printf("FAIL could not read %s\n", [path UTF8String]); failures++; return NO; }
    gdcm::File &file = reader.GetFile();

    NSUInteger rejected = 0;
    std::vector<HorosTagEdit> edits = HorosTagEditsFromEntries(tagAndValues, NSISOLatin1StringEncoding, &rejected);
    if (rejectedOut) *rejectedOut = rejected;

    gdcm::Anonymizer anon;
    anon.SetFile(file);
    bool success = true;

    LOOP

    gdcm::Writer writer;
    writer.SetFileName([path fileSystemRepresentation]);
    writer.SetFile(file);
    if (!writer.Write()) { printf("FAIL could not write %s\n", [path UTF8String]); failures++; return NO; }

    if (reasons) *reasons = refusals;
    return (success && rejected == 0) ? YES : NO;
}

// Reads an element back out of the file on disk.
static bool present(NSString *path, unsigned short group, unsigned short element)
{
    gdcm::Reader reader;
    reader.SetFileName([path fileSystemRepresentation]);
    if (!reader.Read()) return false;
    return reader.GetFile().GetDataSet().FindDataElement(gdcm::Tag(group, element));
}

static std::string valueOf(NSString *path, unsigned short group, unsigned short element)
{
    gdcm::Reader reader;
    reader.SetFileName([path fileSystemRepresentation]);
    if (!reader.Read()) return "<unreadable>";
    const gdcm::DataSet &ds = reader.GetFile().GetDataSet();
    if (!ds.FindDataElement(gdcm::Tag(group, element))) return "<absent>";
    const gdcm::ByteValue *bytes = ds.GetDataElement(gdcm::Tag(group, element)).GetByteValue();
    if (!bytes) return "";   // an element with no value at all
    std::string text(bytes->GetPointer(), bytes->GetLength());
    while (!text.empty() && (text[text.size()-1] == ' ' || text[text.size()-1] == '\0'))
        text.erase(text.size()-1);
    return text;
}

static NSString *pristine;   // the untouched fixture
static NSString *working;    // a disposable copy, remade before each case

static void reset(void)
{
    [NSFileManager.defaultManager removeItemAtPath:working error:nil];
    [NSFileManager.defaultManager copyItemAtPath:pristine toPath:working error:nil];
}

#define TAG(g, e) [DCMAttributeTag group:0x##g element:0x##e]

int main(int argc, const char **argv) { @autoreleasepool {
    pristine = [NSString stringWithUTF8String:argv[1]];
    working = [pristine stringByAppendingString:@".work"];

    // The fixture is what the test says it is.
    reset();
    check(present(working, 0x0008, 0x1030));
    check(valueOf(working, 0x0009, 0x1001) == "original private");
    check(present(working, 0x0009, 0x1002));

    // Removing takes the element out. An entry of one element is a removal.
    reset();
    check(applyEdits(working, @[@[TAG(0008, 1030)]], NULL, NULL) == YES);
    check(present(working, 0x0008, 0x1030) == false);

    // NSNull is the marker the editor already puts in a row it will delete.
    reset();
    check(applyEdits(working, @[@[TAG(0008, 1030), NSNull.null]], NULL, NULL) == YES);
    check(present(working, 0x0008, 0x1030) == false);

    // Emptying is a different request: the element stays, with no value.
    reset();
    check(applyEdits(working, @[@[TAG(0008, 1030), @""]], NULL, NULL) == YES);
    check(present(working, 0x0008, 0x1030));
    check(valueOf(working, 0x0008, 0x1030) == "");

    // And replacing still replaces.
    reset();
    check(applyEdits(working, @[@[TAG(0008, 1030), @"Edited description"]], NULL, NULL) == YES);
    check(valueOf(working, 0x0008, 0x1030) == "Edited description");

    // A private element with a text VR takes a new value and keeps it, which
    // gdcm::Anonymizer::Replace refuses outright.
    reset();
    check(applyEdits(working, @[@[TAG(0009, 1001), @"edited private"]], NULL, NULL) == YES);
    check(valueOf(working, 0x0009, 0x1001) == "edited private");
    // The private creator that owns the block is untouched.
    check(valueOf(working, 0x0009, 0x0010) == "HOROS TEST CREATOR");

    // An odd length is padded, and comes back without the padding.
    reset();
    check(applyEdits(working, @[@[TAG(0009, 1001), @"odd"]], NULL, NULL) == YES);
    check(valueOf(working, 0x0009, 0x1001) == "odd");

    // Emptying and removing a private element are still distinct.
    reset();
    check(applyEdits(working, @[@[TAG(0009, 1001), @""]], NULL, NULL) == YES);
    check(present(working, 0x0009, 0x1001));
    check(valueOf(working, 0x0009, 0x1001) == "");
    reset();
    check(applyEdits(working, @[@[TAG(0009, 1001)]], NULL, NULL) == YES);
    check(present(working, 0x0009, 0x1001) == false);

    // A private element whose value the editor's text cannot express is refused
    // with a reason, and the file keeps what it had.
    reset();
    NSArray *reasons = nil;
    check(applyEdits(working, @[@[TAG(0009, 1002), @"text"]], &reasons, NULL) == NO);
    check(reasons.count == 1);
    check([reasons.firstObject containsString:@"0009,1002"]);
    check([reasons.firstObject containsString:@"OB"]);
    check(present(working, 0x0009, 0x1002));

    // A private element the file does not carry is refused, and said so.
    reset();
    reasons = nil;
    check(applyEdits(working, @[@[TAG(0009, 10ff), @"text"]], &reasons, NULL) == NO);
    check(reasons.count == 1);
    check([reasons.firstObject containsString:@"does not carry"]);

    // One refused element does not cost the others: everything else in the same
    // request is applied, and only the refusal is reported.
    reset();
    reasons = nil;
    check(applyEdits(working, @[@[TAG(0009, 1002), @"text"],
                                @[TAG(0009, 1001), @"still written"],
                                @[TAG(0008, 1030)]], &reasons, NULL) == NO);
    check(valueOf(working, 0x0009, 0x1001) == "still written");
    check(present(working, 0x0008, 0x1030) == false);
    check(reasons.count == 1);

    // An entry that is not shaped like an edit is counted, not applied.
    reset();
    NSUInteger rejected = 0;
    reasons = nil;
    check(applyEdits(working, @[@[TAG(0009, 1001), @42], @[]], &reasons, &rejected) == NO);
    check(rejected == 2);
    check(valueOf(working, 0x0009, 0x1001) == "original private");

    // Every case above rewrote the file; the identifiers still name the same
    // instance, so an edit is an edit and not a new object.
    reset();
    check(applyEdits(working, @[@[TAG(0009, 1001), @"final"]], NULL, NULL) == YES);
    check(valueOf(working, 0x0008, 0x0018) == "1.2.826.0.1.3680043.8.498.10001");
    check(valueOf(working, 0x0020, 0x000e) == "1.2.826.0.1.3680043.8.498.3");

    [NSFileManager.defaultManager removeItemAtPath:working error:nil];
    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("ok\n");
    return 0;
} }
'''

code = code.replace('EXTRACTION', extraction).replace('LOOP', loop)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'fixture.dcm').write_bytes(fixture)
    (path / 'main.mm').write_text(code)
    libraries = ['-lgdcmMSFF', '-lgdcmDICT', '-lgdcmIOD', '-lgdcmDSED', '-lgdcmMEXD',
                 '-lgdcmCommon', '-lgdcmjpeg8', '-lgdcmjpeg12', '-lgdcmjpeg16',
                 '-lgdcmcharls', '-lgdcmopenjp2', '-lgdcmexpat', '-lgdcmuuid',
                 '-lgdcmzlib', '-lsocketxx']
    libraries = [name for name in libraries
                 if (gdcm / 'lib' / ('lib%s.a' % name[2:])).exists()]
    subprocess.run(['xcrun', 'clang++', '-fobjc-arc', '-std=c++14',
                    '-I', str(gdcm / 'include'),
                    str(path / 'main.mm'), '-L', str(gdcm / 'lib'), *libraries,
                    '-framework', 'Foundation', '-framework', 'CoreFoundation',
                    '-o', str(path / 'test')], check=True)
    sys.exit(subprocess.run([str(path / 'test'), str(path / 'fixture.dcm')]).returncode)
