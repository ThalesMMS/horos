#!/usr/bin/env python3
"""Walking the selected rows must carry the previous index, not re-read itself.

The database outline walks an NSIndexSet by hand:

    row = (x == 0) ? [selectedRows firstIndex]
                   : [selectedRows indexGreaterThanIndex: row];

which only works if `row` outlives the iteration. Declared inside the loop body
it was initialised from itself, so every pass after the first asked for the
index greater than whatever was on the stack. One selected row hid it - only
the first pass runs - but two or more meant unifyStudies:, mergeStudies: and
delItem: could act on a study that was never selected.

This checks the declarations are hoisted, and compiles the walk to confirm it
enumerates a selection exactly and in order.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
source = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')

# --- no index may be initialised from itself ---------------------------------
self_referencing = re.findall(
    r'NSInteger\s+(\w+)\s*=\s*\([^)]*\)\s*\?\s*\[\w+ firstIndex\]\s*:\s*\[\w+ indexGreaterThanIndex:\s*\1\s*\]',
    source)
for name in self_referencing:
    failures.append("'%s' is declared and initialised from itself; the previous index "
                    "cannot survive the iteration" % name)

# Every hand-rolled walk must assign, not declare, inside the loop.
walks = re.findall(r'(\w+)\s*=\s*\([^)]*\)\s*\?\s*\[(\w+) firstIndex\]', source)
# Seven of these walks exist; four were self-referencing and three were already
# correct. Do not pin the count - it only rots - but keep the check from going
# vacuous if they are all rewritten away.
if len(walks) < 4:
    failures.append('expected the selected-row walks in BrowserController.m, found %d'
                    % len(walks))

# --- the walk itself, compiled and run ---------------------------------------
code = r'''
#import <Foundation/Foundation.h>
static int check(NSIndexSet *set, NSArray *expected) {
    NSMutableArray *seen = [NSMutableArray array];
    NSIndexSet *selectedRows = set;
    NSInteger row = NSNotFound;
    for (NSInteger x = 0; x < (NSInteger)[selectedRows count]; x++) {
        row = (x == 0) ? [selectedRows firstIndex] : [selectedRows indexGreaterThanIndex: row];
        [seen addObject: @(row)];
    }
    if (![seen isEqualToArray: expected]) {
        printf("FAIL: walked %s, expected %s\n",
               [[seen description] UTF8String], [[expected description] UTF8String]);
        return 1;
    }
    return 0;
}
int main(void) { @autoreleasepool {
    int bad = 0;
    NSMutableIndexSet *one = [NSMutableIndexSet indexSetWithIndex: 7];
    bad |= check(one, @[@7]);

    NSMutableIndexSet *few = [NSMutableIndexSet indexSet];
    NSUInteger scattered[] = {2, 5, 9, 14};
    for (size_t i = 0; i < sizeof(scattered) / sizeof(*scattered); ++i)
        [few addIndex: scattered[i]];
    bad |= check(few, @[@2, @5, @9, @14]);

    NSMutableIndexSet *run = [NSMutableIndexSet indexSetWithIndexesInRange: NSMakeRange(3, 5)];
    bad |= check(run, @[@3, @4, @5, @6, @7]);

    bad |= check([NSIndexSet indexSet], @[]);

    if (!bad) puts("PASS: the walk enumerates the selection exactly and in order");
    return bad;
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-row-walk-') as tmp:
    path = Path(tmp)
    (path / 'main.m').write_text(code)
    build = subprocess.run(
        ['xcrun', 'clang', '-fobjc-arc', '-Werror=uninitialized', '-framework', 'Foundation',
         str(path / 'main.m'), '-o', str(path / 'test')],
        capture_output=True, text=True)
    if build.returncode != 0:
        failures.append('the walk does not compile: %s' % build.stderr[-800:])
    else:
        run = subprocess.run([str(path / 'test')], capture_output=True, text=True)
        sys.stdout.write(run.stdout)
        if run.returncode != 0:
            failures.append('the walk does not enumerate the selection')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: %d selected-row walks carry the previous index' % len(walks))
