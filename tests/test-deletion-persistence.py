#!/usr/bin/env python3
"""A study that was deleted does not come back, and a deletion that could not be
recorded says so.

`-[BrowserController proceedDeleteObjects:tree:]` ended with

    [database save];

and dropped the result. On a volume that is full, or read-only, or gone, the rows
stayed in the store while the outline was reloaded without them: the deletion
looked done, and the studies were there again at the next launch.

The automatic cleaning takes the other approach and is measured to work — with
the index made read-only it stops and says `Auto-clean stopped: study deletion
could not be saved: … Code=513`, and the study is still there afterwards. The
manual path now has to be no worse.
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
failures = []
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
clean = (root / 'Horos/Sources/DicomDatabase+Clean.mm').read_bytes().decode('latin1')


def body(signature, source):
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


# --- the manual deletion has to look at whether it was recorded --------------
proceed = body('- (void) proceedDeleteObjects: (NSArray*) objectsToDelete tree:(NSSet*)treeObjs', browser)
if not proceed:
    failures.append('-proceedDeleteObjects:tree: is gone')
else:
    if '[database save];' in proceed:
        failures.append('the deletion is saved with the result thrown away, so a save that fails '
                        'still empties the outline and the studies come back at the next launch')
    if 'save: &saveError' not in proceed and 'save:&saveError' not in proceed:
        failures.append('nothing captures why the deletion could not be recorded')
    if 'rollback' not in proceed:
        failures.append('a deletion that was not recorded is left in the context, so the outline '
                        'shows a deletion the store never took')
    if 'Delete Failed' not in proceed:
        failures.append('a deletion that was not recorded is not reported to the user')

# --- and the automatic cleaning has to keep the discipline it has ------------
if 'Auto-clean stopped: study deletion could not be saved' not in clean:
    failures.append('the space cleaning no longer stops when a deletion cannot be saved')
if 'Auto-clean stopped: date-based deletion could not be saved' not in clean:
    failures.append('the date cleaning no longer stops when a deletion cannot be saved')
if clean.count('performAtomicChanges:') < 3:
    failures.append('the cleaning no longer commits its deletions atomically, so a partial '
                    'deletion can be left behind')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a deletion that the store did not take is rolled back and reported instead of being '
      'shown as done')
