#!/usr/bin/env python3
"""Import batches refresh the study list and the albums at a bounded rate (#697).

Every indexed batch posts OsirixAddToDBNotification, and the browser answered
each one by refetching every study on the main thread and starting an album
count. Compile the production coalescing methods with short intervals and a
recording outline, post a burst of arrivals, and count the refreshes. Also check
that the album count is marked as running before its thread starts, so a burst
cannot start several counts at once.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
failures = []


def body(signature):
    at = browser.find(signature)
    if at < 0:
        failures.append('%s is gone' % signature)
        return ''
    opening = browser.index('{', at)
    depth = 0
    for index in range(opening, len(browser)):
        if browser[index] == '{':
            depth += 1
        elif browser[index] == '}':
            depth -= 1
            if depth == 0:
                return browser[at:index + 1]
    return ''


methods = '\n'.join(body(s) for s in ('-(void)_refreshDatabaseDisplayAfterImport',
                                      '-(void)_importListRefreshFire',
                                      '-(void)_importAlbumsRefreshFire'))

albums = body('- (void)refreshAlbums')
thread = body('- (void)_computeNumberOfStudiesForAlbumsThread')
if not re.search(r'_computingNumberOfStudiesForAlbums = YES;\s*\[NSThread detachNewThreadSelector:@selector\(_computeNumberOfStudiesForAlbumsThread\)', albums):
    failures.append('the album count is not marked as running before its thread starts')
if re.search(r'if \(_computingNumberOfStudiesForAlbums\)', thread):
    failures.append('the album thread checks the mark its caller has just set, and would never count')

NATIVE = r'''
#import <Cocoa/Cocoa.h>
static const NSTimeInterval HorosImportListRefreshInterval = 0.3, HorosImportAlbumsRefreshInterval = 1.0;
@interface Outline : NSObject
@property NSInteger editedRow;
@end
@implementation Outline
@end
@interface Browser : NSObject {
@public
    Outline *databaseOutline;
    BOOL _refreshDeferredWhileEditing;
    NSTimeInterval _lastImportListRefresh, _lastImportAlbumsRefresh;
    BOOL _importListRefreshPending, _importAlbumsRefreshPending;
    int lists, albums;
}
@end
@implementation Browser
- (NSString*)outlineViewRefresh { lists++; return nil; }
- (void)refreshAlbums { albums++; }
METHODS
@end
static void spin(NSTimeInterval seconds) {
    [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:seconds]];
}
int main(void) { @autoreleasepool {
    Browser *b = [Browser new];
    b->databaseOutline = [Outline new]; b->databaseOutline.editedRow = -1;
    [b _refreshDatabaseDisplayAfterImport];
    NSCAssert(b->lists == 1 && b->albums == 1, @"the first batch of a quiet period is shown at once");
    for (int i = 0; i < 20; i++) { [b _refreshDatabaseDisplayAfterImport]; spin(0.075); }
    spin(1.2);
    printf("20 batches over 1.5 s: %d list refreshes, %d album refreshes\n", b->lists, b->albums);
    NSCAssert(b->lists >= 5 && b->lists <= 8, @"list refreshed about every 0.3 s: %d", b->lists);
    NSCAssert(b->albums >= 2 && b->albums <= 3, @"albums refreshed about every 1 s: %d", b->albums);
    int lists = b->lists;
    b->databaseOutline.editedRow = 3;
    [b _refreshDatabaseDisplayAfterImport];
    NSCAssert(b->lists == lists && b->_refreshDeferredWhileEditing, @"an edit keeps its field editor; the refresh is deferred");
    puts("PASS: a burst of 21 import batches refreshed the list and the albums at bounded rates");
}}
'''.replace('METHODS', methods)

if methods.strip():
    with tempfile.TemporaryDirectory(prefix='horos-import-refresh-') as directory:
        path = Path(directory)
        (path / 'test.m').write_text(NATIVE)
        built = subprocess.run(['xcrun', 'clang', '-framework', 'Cocoa', str(path / 'test.m'), '-o', str(path / 'test')],
                               capture_output=True, text=True)
        if built.returncode:
            failures.append('the refresh methods do not compile: ' + built.stderr[-3000:])
        else:
            run = subprocess.run([str(path / 'test')], capture_output=True, text=True, timeout=60)
            print(run.stdout.strip())
            if run.returncode:
                failures.append('coalescing regression: ' + run.stderr[-1500:])

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: import batches refresh the list at most every interval, the albums less often, one count at a time')
