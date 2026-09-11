#!/usr/bin/env python3
"""The step an import stops on says what went wrong with it.

The report is of an import that parks on "Synchronizing database..." and never
moves. That status is set immediately before the only step that could not say
anything:

    thread.status = NSLocalizedString(@"Synchronizing database...", nil);
    thread.progress = -1;

    if( protectionAgainstReentry == NO)
    {
        protectionAgainstReentry = YES;
        [self.managedObjectContext save:NULL];
        protectionAgainstReentry = NO;
    }

Two things follow from that shape. The error is thrown away, so a save that fails
leaves the panel on an indeterminate bar with nothing said. And a save that
*raises* never clears the flag - the enclosing @catch swallows the exception -
so every later import in the session skips its save in silence, with the images
in the context and never written.

Measured with the store file made unwritable, importing a disc of 15 instances
into a database that already held 10:

    (addFilesDescribedInDictionaries): the database could not be saved: The file
    couldn't be saved because you don't have permission; 15 file(s) are in the
    database folder and not in the index, and rebuilding the database index will
    bring them in
      studies 1  series 2  images 10
      files in DATABASE.noindex: 25

The thread ends (`volumeScanThread: end`), so the panel goes away rather than
parking; nothing was deleted; and after a restart the database still holds its 10
and the 25 files are still there.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')

at = database.find('@"Synchronizing database..."')
if at < 0:
    failures.append('the step that synchronises the database is gone')
else:
    region = re.sub(r'//[^\n]*', '', database[at:at + 3200])
    if 'save:NULL' in region or 'save: NULL' in region:
        failures.append('the save still throws its error away, so the step that an import parks '
                        'on cannot say what went wrong')
    if 'saveError' not in region:
        failures.append('the save does not ask for an error')
    if 'could not be saved' not in region:
        failures.append('a failed save says nothing')
    if 'thread.status' not in region[region.find('could not be saved'):]:
        failures.append('the failure is logged but not shown on the progress panel, which is '
                        'where the user is looking')
    if 'rebuilding the database index' not in region:
        failures.append('a failed save does not say what state it leaves the copied files in')

    guard = region.find('protectionAgainstReentry = YES')
    if guard < 0:
        failures.append('the guard against a re-entrant save is gone')
    else:
        window = region[guard:guard + 1600]
        if '@finally' not in window:
            failures.append('a save that raises leaves the re-entry flag set, and every later '
                            'import in the session then skips its save in silence')
        clear = window.find('protectionAgainstReentry = NO')
        finally_at = window.find('@finally')
        if clear < 0 or clear < finally_at:
            failures.append('the re-entry flag is cleared outside the @finally, so an exception '
                            'still leaves it set')
    tail = region[region.find('protectionAgainstReentry = YES'):]
    if 'another import is saving' not in tail:
        failures.append('a save skipped because another import holds the flag is skipped in '
                        'silence')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the synchronising step names its error, keeps the copied files, and cannot leave the '
      're-entry guard set')
