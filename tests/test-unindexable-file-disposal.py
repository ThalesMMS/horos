#!/usr/bin/env python3
"""A file that cannot be indexed does not stay in the database folder.

The incoming import moves a file into the database folder first and indexes it
afterwards. When the indexing refuses it, it has to leave: deleted, or kept in
NOT READABLE, according to `DELETEFILELISTENER`. That was done only for a file
that opened and produced no dictionary:

    if (curFile)
    {
        curDict = [curFile dicomElements];
        ...
        else  // curDict == nil
        {
            if (dataDirPath && [newFile hasPrefix: dataDirPath]) { delete or move }
        }
    }

A file `-[DicomFile init:]` could not construct at all - a truncated one, say -
fell outside that `if (curFile)` and was left where it was. Measured on an import
of 1204 files with one truncated instance among them:

    (importFilesFromIncomingDir): 1201 file(s) taken from the incoming folder,
                                  1200 indexed, in 1.4 s
      DATABASE.noindex   1201 file(s)
      NOT READABLE       0 file(s)

1201 files for 1200 images, and nothing said. Both failures share one disposal
now, and it says which of the two happened:

    ---- import: 739.dcm could not be indexed; deleted (DELETEFILELISTENER)
      DATABASE.noindex   1200 file(s)

    ---- import: 739.dcm could not be indexed; kept in NOT READABLE
      DATABASE.noindex   1200 file(s)      NOT READABLE  3 file(s)
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')

start = database.find('-(NSArray*)addFilesAtPaths:(NSArray*)paths postNotifications:(BOOL)'
                      'postNotifications dicomOnly:(BOOL)dicomOnly rereadExistingItems:'
                      '(BOOL)rereadExistingItems generatedByOsiriX:(BOOL)generatedByOsiriX '
                      'importedFiles: (BOOL) importedFiles returnArray: (BOOL) returnArray\n{')
if start < 0:
    failures.append('-addFilesAtPaths:... is gone')
else:
    region = re.sub(r'//[^\n]*', '', database[start:database.find('\n-(NSArray*)', start + 10)])

    if 'disposeOfUnreadable' not in region:
        failures.append('there is no single place that gets an unindexable file out of the '
                        'database folder')
    else:
        if region.count('disposeOfUnreadable( newFile)') != 2:
            failures.append('only one of the two ways indexing can refuse a file disposes of it: '
                            'a file that could not be opened at all, and one that opened and '
                            'produced no dictionary (%d of 2)'
                            % region.count('disposeOfUnreadable( newFile)'))
        at = region.find('void (^disposeOfUnreadable)')
        body = region[at:region.find('\n        };', at)]
        if 'hasPrefix: dataDirPath' not in body:
            failures.append('a file outside the database folder would be deleted too')
        if 'DELETEFILELISTENER' not in body:
            failures.append('the preference that decides between deleting and keeping is not read')
        if 'availablePathInDirectory' not in body:
            failures.append('a second unreadable file of the same name is moved onto the first, '
                            'and the failed move then deletes it')
        for outcome in ('deleted (DELETEFILELISTENER)', 'kept in', 'could not be deleted',
                        'could not be kept'):
            if outcome not in body:
                failures.append('the disposal does not say what happened when it %r' % outcome)

    if 'Unreadable file' in region:
        failures.append('the old branch is still here beside the new one')

if 'static NSString *availablePathInDirectory( NSString *directory, NSString *name);' not in database:
    failures.append('the helper is used before it is declared')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: whichever way indexing refuses a file, it leaves the database folder and says how')
