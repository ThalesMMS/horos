#!/usr/bin/env python3
"""A medium that was not written must not sound and look like one that was.

createDMG only logged when the *task* failed to finish, and HorosRunTaskUntilExit
answers YES for a task that finishes whatever its exit status - so hdiutil
reporting a full destination was ignored, and the window played the success sound
and closed with no disc image anywhere. The USB path was worse: it erases the
volume first and then discarded the copy error.
"""
from pathlib import Path
import re, sys

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/BurnerWindowController.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/BurnerWindowController.h').read_bytes().decode('latin1')
failures = []

if '- (BOOL) createDMG:' not in source:
    failures.append('createDMG no longer reports whether it worked')
if 'makeImageTask.terminationStatus != 0' not in source:
    failures.append("the disc image task's exit status is ignored again")
if '- (BOOL) saveOnVolume' not in source or '- (BOOL)saveOnVolume;' not in header:
    failures.append('saveOnVolume no longer reports whether it worked')
if 'byReplacingExisting: YES error: &copyError' not in source:
    failures.append('the copy to the volume discards its error again')

# The success sound and the close must be behind the failure check.
start = source.index('self.buttonsDisabled = NO;\n        runBurnAnimation = NO;\n        burning = NO;')
tail = source[start:start + 1800]
if 'if( failed)' not in tail:
    failures.append('the end of a burn no longer distinguishes a failure')
if tail.index('if( failed)') > tail.index('Glass.aiff'):
    failures.append('the success sound plays before the failure is considered')
if 'The medium was not created' not in tail:
    failures.append('a failed burn no longer says so')

# Every diskutil wait has a deadline; the three unbounded polls are gone.
volume = source[source.index('- (BOOL) saveOnVolume'):source.index('- (void)burnCD:')]
if re.search(r'while\(\s*\[\s*\w+ isRunning\s*\]\s*\)', volume):
    failures.append('a diskutil task is polled with no deadline again')
if 'HorosRunTaskUntilExit( rename, 120' not in source:
    failures.append('renaming the volume is no longer bounded')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('PASS: both destinations report a failure, the success sound is behind that check, '
      'and no diskutil wait is unbounded')
