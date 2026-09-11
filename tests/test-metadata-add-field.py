#!/usr/bin/env python3
"""A tag added in the editor is the tag the outline row is looked up by.

Both strings are taken from the production sources — the one the Add sheet
searches with, and the one DCMAttribute writes into the row — and compared with
the same case-sensitive test the lookup uses.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

controller = (root / 'Horos/Sources/XMLController.m').read_bytes().decode('latin1')
attribute = (root / 'DCM Framework/DCMAttribute.m').read_bytes().decode('latin1')

# What the Add sheet searches with.
search = re.search(r'NSString \*searchGpEl = (.*?);\n', controller)
if not search:
    failures.append('XMLController.m: the Add sheet no longer builds a tag to search for')

# What the row carries, and the comparison that decides whether it matched.
row = re.search(r'attributeWithName:@"attributeTag" stringValue: *(.*?)\]', attribute)
if not row:
    failures.append('DCMAttribute.m: the row no longer carries an attributeTag')
if 'attributeForName:@"attributeTag"] stringValue] isEqualToString: searchGpEl' not in controller:
    failures.append('XMLController.m: the row lookup changed shape; this test is stale')

code = r'''
#import <Foundation/Foundation.h>
#import "DCMAttributeTag.h"

static int failures;

int main(void) { @autoreleasepool {
    // Tags an editor user would add. The first two carry hex letters.
    struct { unsigned group, element; const char *name; } cases[] = {
        { 0x0008, 0x103E, "Series Description" },
        { 0x0018, 0x1030, "Protocol Name" },
        { 0x0008, 0x1030, "Study Description" },
        { 0x0010, 0x0010, "Patient Name" },
        { 0x0010, 0x0020, "Patient ID" },
        { 0x00E1, 0x10C2, "a private one" },
        { 0xFFFF, 0xFFFF, "all letters" },
    };

    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        unsigned group = cases[i].group, element = cases[i].element;
        DCMAttributeTag *tag = [[DCMAttributeTag alloc] initWithGroup: group element: element];

        NSString *searchGpEl = SEARCH;   // what the Add sheet looks for
        NSString *inTheRow = ROW;        // what the outline row carries

        // The production lookup is isEqualToString:, which is case sensitive.
        if (![inTheRow isEqualToString: searchGpEl]) {
            printf("FAIL %s: the sheet searches for %s and the row carries %s\n",
                   cases[i].name, [searchGpEl UTF8String], [inTheRow UTF8String]);
            failures++;
        }
    }

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("ok\n");
    return 0;
} }
'''

if not failures:
    search_expression = search.group(1)
    row_expression = row.group(1)
    # In the production code both read from a `tag` built from the same group
    # and element; the harness supplies that tag.
    row_expression = row_expression.replace('self.attrTag', 'tag')
    code = code.replace('SEARCH', search_expression).replace('ROW', row_expression)

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        (path / 'main.m').write_text(code)
        build = subprocess.run(['xcrun', 'clang', '-fno-objc-arc',
                                '-I', str(root / 'DCM Framework'),
                                str(path / 'main.m'),
                                str(root / 'DCM Framework/DCMAttributeTag.m'),
                                # DCMAttributeTag resolves 2011 tag aliases through this.
                                str(root / 'DCM Framework/DCMTagNameAlias.m'),
                                str(root / 'DCM Framework/DCMTagDictionary.m'),
                                str(root / 'DCM Framework/DCMTagForNameDictionary.m'),
                                '-framework', 'Foundation', '-framework', 'Cocoa',
                                '-o', str(path / 'test')], capture_output=True, text=True)
        if build.returncode != 0:
            print(build.stderr)
            failures.append('the extracted expressions do not compile')
            ran = 1
        else:
            ran = subprocess.run([str(path / 'test')]).returncode
else:
    ran = 1

for failure in failures:
    print('FAIL: %s' % failure)
sys.exit(1 if (failures or ran) else 0)
