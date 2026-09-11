#!/usr/bin/env python3
"""Removing a DICOM element, emptying it and replacing it are three requests."""
from pathlib import Path
import subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/XMLControllerDCMTKCategory.mm'
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
          if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')

start = source.index('typedef struct')
# Stop before the GDCM helper that was added below the parser: this test builds
# the parser on its own, with no DCMTK or GDCM headers.
end = source.index('static bool HorosReplacePrivateValue')
parser = source[start:end]

code = r'''
#import <Foundation/Foundation.h>
#include <string>
#include <vector>

// Stands in for the DCM framework's tag: the parser only reads group/element.
@interface DCMAttributeTag : NSObject
@property unsigned short group;
@property unsigned short element;
+ (instancetype) group:(unsigned short)g element:(unsigned short)e;
@end
@implementation DCMAttributeTag
+ (instancetype) group:(unsigned short)g element:(unsigned short)e {
    DCMAttributeTag *t = [DCMAttributeTag new]; t.group = g; t.element = e; return t;
}
@end

PARSER

#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)

int main(){@autoreleasepool{
 NSStringEncoding latin = NSISOLatin1StringEncoding;
 DCMAttributeTag *comment = [DCMAttributeTag group:0x0032 element:0x4000];
 DCMAttributeTag *name = [DCMAttributeTag group:0x0010 element:0x0010];
 NSUInteger rejected = 0;

 // One element removes; two replace, and an empty second element is a value.
 std::vector<HorosTagEdit> edits = HorosTagEditsFromEntries(
     @[ @[comment], @[name, @"DOE^JOHN"], @[comment, @""] ], latin, &rejected);
 check(rejected == 0);
 check(edits.size() == 3);
 check(edits[0].group == 0x0032 && edits[0].element == 0x4000 && edits[0].removes);
 check(!edits[1].removes && edits[1].group == 0x0010 && edits[1].value == "DOE^JOHN");
 check(!edits[2].removes && edits[2].value == "");

 // The shape the callers used to build — a flattened pair — is not an edit
 // list. The previous loop declared each element as NSArray* and sent it
 // -count, which a tag object does not answer, so the whole write raised and
 // was swallowed by the caller's @catch.
 check(![comment respondsToSelector:@selector(count)]);
 rejected = 0;
 edits = HorosTagEditsFromEntries(@[ comment, @"a comment" ], latin, &rejected);
 check(edits.empty() && rejected == 2);

 // Nothing here may raise, and nothing may be silently turned into an edit.
 // NSNull in the value position is the exception: that is how the metadata
 // editor marks a row for deletion, so it is a removal rather than a reject.
 rejected = 0;
 edits = HorosTagEditsFromEntries(
     @[ @[], @[@"0032,4000", @"x"], @[comment, @42], @[comment, [NSNull null]],
        (id)@"not an entry", (id)[NSNull null], @[[NSNull null], @"x"] ],
     latin, &rejected);
 check(edits.size() == 1);
 check(edits[0].removes && edits[0].group == 0x0032 && edits[0].element == 0x4000);
 check(rejected == 6);

 // Extra elements past the value are ignored rather than rejected.
 rejected = 0;
 edits = HorosTagEditsFromEntries(@[ @[name, @"A", @"ignored"] ], latin, &rejected);
 check(rejected == 0 && edits.size() == 1 && !edits[0].removes && edits[0].value == "A");

 // A value the file's character set cannot hold is reported, not truncated.
 rejected = 0;
 edits = HorosTagEditsFromEntries(@[ @[name, @"你好"] ], latin, &rejected);
 check(edits.empty() && rejected == 1);
 rejected = 0;
 edits = HorosTagEditsFromEntries(@[ @[name, @"你好"] ], NSUTF8StringEncoding, &rejected);
 check(rejected == 0 && edits.size() == 1);

 // An empty list is not an error, and a null out-parameter is allowed.
 check(HorosTagEditsFromEntries(@[], latin, NULL).empty());
 check(HorosTagEditsFromEntries(nil, latin, NULL).empty());

 NSLog(@"PASS: one element removes, two replace including with an empty value, and flattened, malformed or unencodable entries are counted instead of raising");
}}
'''.replace('PARSER', parser)

with tempfile.TemporaryDirectory(prefix='horos-tag-edits-') as folder:
    p = Path(folder)
    (p / 'test.mm').write_text(code)
    subprocess.run(['xcrun', 'clang++', '-fno-objc-arc', '-std=c++17',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-framework', 'Foundation', str(p / 'test.mm'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
