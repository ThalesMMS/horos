#!/usr/bin/env python3
"""Studies arriving do not reload the outline under someone typing in it.

`-[BrowserController refreshDatabase:]`, the timer-driven refresh, has always
refused to run while a cell is being edited:

    if( DatabaseIsEdited) return;
    if( [databaseOutline editedRow] != -1) return;

The notification-driven refresh had no such guard. `OsirixAddToDBNotification`
is posted for every batch that lands, and `-_observeDatabaseAddNotification:`
called `-outlineViewRefresh` straight away — reloading the outline tears down the
field editor, so the partial text and the insertion point go. Studies arrive one
after another, which is the loss of focus per arrival the reports describe.
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
failures = []
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/BrowserController.h').read_bytes().decode('latin1')


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


# --- the refresh that arrivals trigger has to stay out of an edit ------------
refresh = body('-(void)_refreshDatabaseDisplay', browser)
if not refresh:
    failures.append('-_refreshDatabaseDisplay is gone')
else:
    if 'editedRow' not in refresh:
        failures.append('the refresh that a study arriving triggers does not ask whether a cell '
                        'is being edited, so it reloads the outline under the field editor')
    if 'outlineViewRefresh' not in refresh:
        failures.append('the refresh no longer refreshes')

# --- and the arrival notification has to go through it ----------------------
arrival = body('-(void)_observeDatabaseAddNotification:', browser)
if not arrival:
    failures.append('-_observeDatabaseAddNotification: is gone')
else:
    if '_refreshDatabaseDisplay' not in arrival:
        failures.append('the arrival notification refreshes the outline directly, bypassing the '
                        'guard entirely')
    if 'outlineViewRefresh' in arrival:
        failures.append('the arrival notification still calls -outlineViewRefresh itself')

# --- what was deferred has to happen once the edit is over -------------------
if '_refreshDeferredWhileEditing' not in header:
    failures.append('nothing remembers that a refresh was skipped, so the outline stays stale '
                    'until something else happens to refresh it')
deferred = body('-(void)_refreshDatabaseDisplayIfDeferred', browser)
if not deferred:
    failures.append('there is no way to run the refresh that was deferred')
else:
    if '_refreshDeferredWhileEditing' not in deferred:
        failures.append('the deferred refresh does not check whether one was deferred')
    if 'editedRow' not in deferred:
        failures.append('the deferred refresh can run while the edit is still open, which is the '
                        'thing it exists to avoid')

commit = body('- (void) setDatabaseValue:(id) object item:(id) item forKey:(NSString*) key', browser)
if not commit:
    failures.append('-setDatabaseValue:item:forKey: is gone')
elif '_refreshDatabaseDisplayIfDeferred' not in commit:
    failures.append('committing an edit does not catch the outline up on what arrived meanwhile')

# --- the timer-driven refresh must keep its own guard ------------------------
timer = body('- (void)refreshDatabase: (id)sender', browser)
if timer and 'editedRow' not in timer:
    failures.append('the timer-driven refresh has lost the guard it always had')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a study arriving defers the outline reload while a cell is being edited, and the '
      'deferred reload happens once the edit is over')
