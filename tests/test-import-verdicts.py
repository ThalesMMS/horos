#!/usr/bin/env python3
"""Every file put in the incoming folder ends as a study or as a stated refusal.

Measured before the change, five files dropped into the incoming folder of a
running build: two valid instances became a study, and

  - notes.txt, photo.jpg and a truncated DICOM vanished, with nothing logged and
    nothing in the NOT READABLE folder - which did not exist, because nothing
    ever created it, so every move into it failed and the fallback deleted the
    file. The preference meant to keep unreadable files kept nothing;
  - a zero-length file stayed in the incoming folder for ever: it matched neither
    the directory branch nor the `size > 0` branch, so every scan enumerated it
    and skipped it again.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')


def body(signature, source=None):
    source = source if source is not None else database
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


# --- the folder that keeps unreadable files has to exist ----------------------
errors = body('-(NSString*)errorsDirPath')
if not errors:
    failures.append('-errorsDirPath is gone')
elif 'confirmDirectoryAtPath' not in errors:
    failures.append('nothing creates the NOT READABLE folder, so every move into it fails and '
                    'the file is deleted instead')

# --- a file that cannot be indexed says so, whichever way it goes -------------
branch = body('else // DELETE or MOVE THIS UNKNOWN FILE ?')
if not branch:
    failures.append('the branch that handles a file that is not indexable is gone')
else:
    logs = re.findall(r'NSLog\(\s*@"---- import: [^"]*"', branch)
    if len(logs) < 3:
        failures.append('a file that cannot be indexed is not named in all three outcomes '
                        '(deleted, kept, or could not be kept): %d of 3' % len(logs))
    if 'DELETEFILELISTENER' not in branch:
        failures.append('the preference that decides between deleting and keeping is gone')
    if 'moveError' not in branch:
        failures.append('a move that fails does not say why before deleting the file')
    # Two archives can each hold a readme.txt. Moving the second onto the first
    # fails, and the fallback deletes it - so the preference that is meant to
    # keep unreadable files silently keeps only the first of each name.
    if 'availablePathInDirectory' not in branch:
        failures.append('a second file of the same name is moved onto the first, and the failed '
                        'move deletes it although the preference says to keep it')

# --- and an empty file does not sit there for ever ---------------------------
if 'longLongValue] == 0' not in database:
    failures.append('a zero-length file still matches no branch and stays in the incoming folder')
else:
    at = database.find('longLongValue] == 0')
    window = database[at:at + 900]
    if 'NSFileModificationDate' not in window:
        failures.append('an empty file is removed without asking how long it has been empty, so a '
                        'transfer in progress could be destroyed')
    if 'timeIntervalSinceNow' not in window:
        failures.append('there is no age test on an empty file')
    if 'removeItemAtPath' not in window:
        failures.append('an empty file is still not removed')
    if 'is empty' not in window:
        failures.append('an empty file is removed without saying so')

# The two branches must stay in this order, or the empty case never runs.
empty_at = database.find('longLongValue] == 0')
nonempty_at = database.find('longLongValue] > 0\n                {')
if nonempty_at < 0:
    nonempty_at = database.find('objectForKey:NSFileSize] longLongValue] > 0')
if empty_at > 0 and nonempty_at > 0 and empty_at > nonempty_at:
    failures.append('the empty-file branch comes after the one that requires a size, so it never '
                    'runs')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a file that cannot be indexed is named and kept where the preference says, and an '
      'empty one is named and removed instead of being enumerated for ever')
