#!/usr/bin/env python3
"""The parsed-file cache and the preview's pixel reuse follow the file revision (#603).

`DCMPix` shares one parsed, memory-mapped `DCMObject` per source file across
every pix that reads it, in a process-wide dictionary that used to be keyed by
the pathname. While any pix for a path was alive (a browser preview, a second
viewer, a 4D set), a new pix for the same path — after a re-import, a rename
over the path or a reused database number — was served the previous file's
mapping: old geometry, old rescale, and pixels from a mapping of a file that
no longer exists. The browser also copied pixels from an open viewer by path.

Source level, on the real methods: every access to `cachedDCMFrameworkFiles`
inside `loadDICOMDCMFramework` uses `parsedFileCacheKey`, the release path uses
the key that was stored, the decoded pixels record their file revision, the
revert and the copy carry it, and the preview refuses a loaded frame whose
file no longer matches the disk. Object level: the key and the revision come
from `HorosFileRevision`, exercised by test-file-revision.py.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def read(path):
    """The working tree, or `<revision>:<path>` when a git revision is given (negative control)."""
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


pix = read('Horos/Sources/DCMPix.m')
header = read('Horos/Sources/DCMPix.h')
browser = read('Horos/Sources/BrowserController.m')
failures = []


def method(source, signature, terminator='\n}\n'):
    start = source.find(signature)
    if start < 0:
        return ''
    return source[start:source.find(terminator, start) + len(terminator)]


# --- the cache is keyed by revision, everywhere it is touched ----------------
load = method(pix, '- (BOOL)loadDICOMDCMFramework\n')
if not load:
    failures.append('loadDICOMDCMFramework is gone from DCMPix.m')
else:
    if 'NSString *parsedFileKey = [self parsedFileCacheKey];' not in load:
        failures.append('loadDICOMDCMFramework does not compute the parsed-file key')
    for access in re.finditer(r'cachedDCMFrameworkFiles (objectForKey|setObject:[^\]]*forKey|valueForKey):\s*([^\]\s]+)', load):
        if access.group(2) != 'parsedFileKey':
            failures.append('loadDICOMDCMFramework still keys the cache by %s' % access.group(2))
    if load.count('cachedFileKey = [parsedFileKey retain];') != 2:
        failures.append('both the hit and the miss must remember the key they used (found %d)' % load.count('cachedFileKey = [parsedFileKey retain];'))

clear = method(pix, '- (void) clearCachedDCMFrameworkFiles\n')
if 'NSString *key = cachedFileKey ?: self.srcFile;' not in clear or 'removeObjectForKey:key]' not in clear:
    failures.append('clearCachedDCMFrameworkFiles must release under the key that stored the group')
if 'cachedFileKey = nil;' not in clear:
    failures.append('clearCachedDCMFrameworkFiles must forget the key once the group is released')

key = method(pix, '- (NSString*) parsedFileCacheKey\n')
if '[HorosFileRevision cacheKeyForPath: self.srcFile]' not in key or 'return self.srcFile;' not in key:
    failures.append('parsedFileCacheKey must ask HorosFileRevision and fall back to the path')

# --- decoded pixels remember the file they came from -------------------------
check_load = method(pix, '- (void) CheckLoadIn\n', '\n}\n\n- (NSString*) parsedFileCacheKey')
if 'loadedFileRevision = [[HorosFileRevision alloc] initWithPath: self.srcFile];' not in check_load:
    failures.append('CheckLoadIn does not record the file revision of the decoded pixels')
if check_load.find('[loadedFileRevision release];') > check_load.find('loadedFileRevision = [[HorosFileRevision alloc]'):
    failures.append('the previous revision must be released before a new one is recorded')

revert = method(pix, '- (void) revert:(BOOL) reloadAnnotations\n')
if '[loadedFileRevision release];' not in revert or 'loadedFileRevision = nil;' not in revert:
    failures.append('revert: must forget the file revision with the pixels')

copy = method(pix, '- (id)copyWithZone:(NSZone *)zone\n')
if 'copy->loadedFileRevision = [self->loadedFileRevision retain];' not in copy:
    failures.append('a copy of decoded pixels must carry their file revision')

dealloc = method(pix, '- (void) dealloc\n')
for ivar in ('cachedFileKey', 'loadedFileRevision'):
    if '[%s release];' % ivar not in dealloc:
        failures.append('dealloc leaks %s' % ivar)

matches = method(pix, '- (BOOL) loadedFileMatchesDisk\n')
if 'return fImage == nil;' not in matches or 'matchesDisk]' not in matches:
    failures.append('loadedFileMatchesDisk must trust nothing decoded without a record and ask the disk otherwise')

for declaration in ('- (NSString*) parsedFileCacheKey;', '- (id) loadedFileRevision;', '- (BOOL) loadedFileMatchesDisk;',
                    'NSString\t\t\t*cachedFileKey;', 'id\t\t\t\t\tloadedFileRevision;'):
    if declaration not in header:
        failures.append('DCMPix.h lacks %r' % declaration)

# --- the preview does not copy pixels of a file that changed -----------------
reuse = method(browser, '- (DCMPix*) getDCMPixFromViewerIfAvailable: (NSString*) pathToFind frameNumber: (int) frameNumber expectedFrame:')
if '[dcmPix loadedFileMatchesDisk] == NO' not in reuse:
    failures.append('the browser reuses a viewer frame without checking the file on disk')
if reuse.find('[dcmPix CheckLoad];') > reuse.find('loadedFileMatchesDisk'):
    failures.append('the disk check must come after CheckLoad, or an unloaded pix is judged before it has a revision')
if 'refusalForReusingFileWithLoaded:' not in reuse:
    failures.append('the refusal to reuse must say why (HorosFileRevision refusal)')
if not re.search(r'else if\( \[dcmPix isLoaded\]\)\s*\{\s*DCMPix \*dcmPixCopy = \[\[vPixList objectAtIndex: i\] copy\];', reuse):
    failures.append('the copy must only be taken when the pix is loaded and current')

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: the parsed-file cache and the preview reuse are keyed by file revision')
