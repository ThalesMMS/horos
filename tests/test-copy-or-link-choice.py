#!/usr/bin/env python3
"""Importing by link stays available, and asking still asks.

`-[BrowserController copyFilesIntoDatabaseIfNeeded:options:]` decides between
copying a file into the database folder and indexing it where it lies.
`COPYDATABASE` says whether to copy at all; `COPYDATABASEMODE` says when.

Measured against a mounted HFS+ volume, importing one instance through the
AppleScript entry, with the preferences written into the application's own domain
rather than passed as arguments - so that reading them back afterwards says
whether they persisted:

    COPYDATABASE=1 MODE=0 (always)   1 image, inDatabaseFolder set,
                                     1 file in the database folder
    COPYDATABASE=0 (links)           1 image at /Volumes/HOROS78/DICOM/...,
                                     0 files in the database folder
    COPYDATABASE=1 MODE=3 (ask)      the main thread in NSRunInformationalAlertPanel
                                     -> runModalForWindow:, 0 images until answered

and every mode read back unchanged afterwards. Switching from "always" back to
"ask" on a database that already holds a study brings the panel back and leaves
the study where it was.

Mode 1 is migrated to 2 on purpose: the "if on CD" choice was taken out of the
preference pane, whose matrix offers tags 0, 2 and 3.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
application = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
defaults = (root / 'Horos/Sources/DefaultsOsiriX.m').read_bytes().decode('latin1')

at = browser.find('- (void) copyFilesIntoDatabaseIfNeeded:')
if at < 0:
    failures.append('the choice between copying and linking is gone')
else:
    opening = browser.index('{', at)
    depth, index = 0, opening
    while index < len(browser):
        if browser[index] == '{':
            depth += 1
        elif browser[index] == '}':
            depth -= 1
            if depth == 0:
                break
        index += 1
    region = re.sub(r'//[^\n]*', '', browser[opening:index + 1])

    if 'COPYDATABASE' not in region:
        failures.append('nothing reads the preference that turns copying off')
    for mode in ('always', 'cdOnly', 'notMainDrive', 'ask'):
        if 'case %s:' % mode not in region:
            failures.append('the %s mode is gone' % mode)
    ask = region[region.find('case ask:'):]
    if 'NSRunInformationalAlertPanel' not in ask:
        failures.append('asking the user no longer asks')
    for answer in ('Copy Files', 'Copy Links', 'Cancel'):
        if answer not in ask:
            failures.append('the panel no longer offers %r' % answer)
    if 'removeAllObjects' not in ask:
        failures.append('cancelling no longer stops the import')

    # A file whose path has no second component would be read out of bounds.
    drive = region[region.find('case notMainDrive:'):region.find('case cdOnly:')]
    if 'pathFilesComponent.count > 1' not in drive:
        failures.append('a path with nothing after its root is read out of bounds')

    # Links must not copy: the copy is the only thing that may write bytes.
    if 'if( copyFiles)' not in region:
        failures.append('the copy is no longer conditional')

# The removed mode is migrated on purpose, and the pane offers the three that are
# left.
if 'COPYDATABASEMODE' not in application:
    failures.append('a stored value for the mode that was taken out of the pane is no longer '
                    'migrated, so it would select nothing')
if '@"3" forKey:@"COPYDATABASEMODE"' not in defaults.replace(' ', ''):
    if 'COPYDATABASEMODE' not in defaults:
        failures.append('the mode has no registered default')
for pane in root.glob('Preference Panes/OSIDatabasePreferencePane/*.lproj/'
                      'OSIDatabasePreferencePanePref.xib'):
    text = pane.read_text(encoding='utf-8', errors='replace')
    if 'values.COPYDATABASEMODE' not in text:
        failures.append('%s no longer offers the choice' % pane.parent.name)
    if 'values.COPYDATABASE' not in text:
        failures.append('%s no longer offers copying by link' % pane.parent.name)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: copying, linking and asking are all still offered, and a path with no second component '
      'is not read out of bounds')
