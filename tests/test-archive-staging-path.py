#!/usr/bin/env python3
"""An archive dropped on the browser is expanded where only this process can see.

`-[BrowserController addFilesAndFolderToDatabase:]` unzipped into
`/tmp/unzip_folder`: one fixed, world-visible path, removed and recreated on
every archive with every result ignored.

  - `/tmp` is writable by everyone and sticky, so removing a directory another
    user owns fails and `createDirectoryAtPath:withIntermediateDirectories:YES`
    then succeeds on *their* directory — whose contents were moved into the
    database;
  - two archives in one drop, or two copies of Horos, used the same path at the
    same time;
  - the destination name came from `static int uniqueZipFolder = 1`, which
    restarts every launch, so the move failed against a folder still waiting to
    be imported and the expansion was lost without a word, to be deleted by the
    next archive.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')


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


# Comments quote the old code, so match what is compiled, not what is written
# about it.
code = re.sub(r'//[^\n]*', '', browser)

if 'unzip_folder' in code:
    failures.append('an archive is still expanded at a fixed path shared with every other user '
                    'and process on the machine')
if 'uniqueZipFolder' in code:
    failures.append('the destination name still comes from a counter that restarts every launch, '
                    'so it collides with a folder that has not been imported yet')

expand = body('- (void) expandArchiveIntoIncomingFolder: (NSString*) archive', browser)
if not expand:
    failures.append('there is no single place that expands an archive dropped on the browser')
else:
    if 'tmpDirPath' not in expand:
        failures.append('the working directory is not the per-user temporary directory')
    if 'UUID' not in expand:
        failures.append('the working directory or the destination is not unique, so two archives '
                        'at once share one')
    if 'NSFilePosixPermissions' not in expand:
        failures.append('the working directory is created readable by everyone')
    if expand.count('error: &error') < 2 and expand.count('error:&error') < 2:
        failures.append('the results of creating and moving the expansion are not looked at, '
                        'which is how an expansion is lost without a word')
    if 'could not be handed to the import folder' not in expand:
        failures.append('an expansion that could not be handed over is not reported')
    if 'fileExistsAtPath: staging' not in expand:
        failures.append('the cleanup does not check whether the move already took the folder, so '
                        'it can delete an expansion that is waiting to be imported')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: an archive is expanded in a private directory of its own and handed over under a name '
      'nothing else can hold, with both steps checked')
