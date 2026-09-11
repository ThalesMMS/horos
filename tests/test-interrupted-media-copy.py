#!/usr/bin/env python3
"""A copy cut short leaves an import that is smaller, not one that is hidden.

`-[DicomDatabase copyFilesThread:]` copies in batches and hands each batch to an
operation queue that indexes it. The files in a batch are already inside the
database folder by then - the indexing does not touch the medium at all - but the
wait at the end of the copy cancelled those operations:

    while (queue.operationCount)
    {
        [NSThread sleepForTimeInterval:0.05];
        if( [[NSThread currentThread] isCancelled])
            [queue cancelAllOperations];
    }

Pulling a disc out cancels the scan thread, which cancels the copy thread, which
cancelled the batch holding everything copied so far. Measured on a 155 MB disc
of 1200 instances pulled out one second into the import:

    (copyFilesThread): 1200 file(s) offered, 373 copied, 0 indexed, 0 could not be copied
      studies 0  series 0  images 0
      files in DATABASE.noindex: 373

373 files in the database folder that no row pointed at, and nothing said. The
counts are kept now, and cancelling stops the copying rather than the indexing.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')

start = database.find('-(void)copyFilesThread:(NSDictionary*)dict\n{')
if start < 0:
    failures.append('-copyFilesThread: is gone')
else:
    region = re.sub(r'//[^\n]*', '',
                    database[start:database.find('\n-(void)_notificationImagesAdded:', start)])

    # --- what is already copied is indexed ------------------------------------
    at = region.find('while (queue.operationCount)')
    if at < 0:
        failures.append('the copy no longer waits for its indexing to finish')
    else:
        wait = region[at:at + 400]
        if 'cancelAllOperations' in wait:
            failures.append('cancelling the copy still throws away the indexing of the files it '
                            'already copied, leaving them in the database folder with no row '
                            'pointing at them')
    if 'cancelAllOperations' in region:
        failures.append('something still cancels the queued indexing')

    # --- and the two counts are kept and said ---------------------------------
    for name in ('copiedTotal', 'indexedTotal'):
        if name not in region:
            failures.append('the copy does not count how many files were %s'
                            % ('copied' if name == 'copiedTotal' else 'indexed'))
    if 'copiedTotal += copiedFiles.count' not in region:
        failures.append('the count of copied files is never added up')
    if 'indexedTotal += objects.count' not in region:
        failures.append('the count of indexed files is never added up')
    at = region.find('copyFilesThread):')
    if at < 0:
        failures.append('an import that took less than it was given says nothing')
    else:
        line = region[max(0, at - 300):at + 500]
        if 'copiedTotal != indexedTotal' not in line:
            failures.append('the report is only written when a copy failed, so an import cut '
                            'short says nothing')
        if 'file(s) offered' not in line or 'copied' not in line or 'indexed' not in line:
            failures.append('the report does not give offered, copied and indexed')
    # The counts are added from an operation-queue thread while the copy thread
    # reads them, so they need a lock of their own.
    if '@synchronized' not in region[region.find('copiedTotal += copiedFiles.count') - 200:
                                     region.find('copiedTotal += copiedFiles.count')]:
        failures.append('the counts are written from the indexing thread without a lock')

    # --- a copy that fails still tells the user -------------------------------
    if 'could not be copied and were not indexed' not in region:
        failures.append('the message about files that could not be copied is gone')

# --- and the scan does not report a stopped copy as a finished one ------------
scan = re.sub(r'//[^\n]*', '',
              (root / 'Horos/Sources/DicomDatabase+Scan.mm').read_bytes().decode('latin1'))
at = scan.find('[timing end: @"copying"')
if at < 0:
    failures.append('the copy is no longer timed')
else:
    window = scan[max(0, at - 400):at + 400]
    if 'copyFilesThread.isCancelled' not in window:
        failures.append('a copy that was stopped part way is still reported as having copied '
                        'every file it was given')
    if 'stopped before it finished' not in scan:
        failures.append('nothing says the copy was stopped')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a copy cut short indexes what it already took, and says how much of what it was '
      'offered arrived')
