#!/usr/bin/env python3
"""Two series are two windows, and the preference that says otherwise is asked.

Three things have to hold together for several series to be several viewers, and
each was measured at runtime before being written down here.

macOS groups new windows into tabs when the user sets "Prefer tabs: always".
`AppController` opts the whole application out, so with that global preference
set to `always` four open viewers reported `tabbedWindows` nil and four distinct
single-window tab groups.

Opening a *series* must make a window rather than reuse one: `databaseOpenStudy:`
passes `viewer:nil`, and `openViewerFromImages:` only calls `changeImageData:` on
a viewer it was handed.

And the XML-RPC open path must keep *asking* whether to close what is already
open, instead of closing it unconditionally. That preference is the Listener
checkbox "Automatically close all 2D Viewers before displaying studies with
XML-RPC orders", registered as 1. With it on, three DisplaySeries calls leave one
viewer - the debugger showed `closeAllWindows` called from
`_onMainThreadOpenObjectsWithIDs:` - and with it off the same three calls leave
three, tiled side by side. Hard-wiring that call would take the only scriptable
way to open several viewers with it.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


application = strip((root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1'))
browser = strip((root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1'))
rpc = strip((root / 'Horos/Sources/XMLRPCMethods.mm').read_bytes().decode('latin1'))

# --- the application refuses macOS window tabs -------------------------------
tabbing = re.search(r'NSWindow\s*\.\s*allowsAutomaticWindowTabbing\s*=\s*(\w+)', application)
if not tabbing:
    failures.append('nothing switches off automatic window tabbing, so "Prefer tabs: always" '
                    'collects the viewers into one tabbed window')
elif tabbing.group(1) != 'NO':
    failures.append('automatic window tabbing is set to %r rather than NO' % tabbing.group(1))
else:
    before = application[:tabbing.start()]
    if 'applicationDidFinishLaunching' not in before:
        failures.append('the tabbing policy is set outside application start-up, so windows made '
                        'earlier would still be tabbed')

# --- opening a series makes a viewer rather than taking one ------------------
at = browser.find('- (void) databaseOpenStudy: (NSManagedObject*) item')
opening = browser[at:at + 1400] if at >= 0 else ''
if not opening:
    failures.append('databaseOpenStudy: is gone')
elif not re.search(r'viewerDICOMInt\s*:\s*NO\s+dcmFile:[^;]*viewer:\s*nil', opening):
    failures.append('opening a series no longer asks for a new viewer, so the second series would '
                    'replace the first in the same window')

# --- and the documented preference is still consulted ------------------------
at = rpc.find('_onMainThreadOpenObjectsWithIDs:(NSArray*)objectIDs')
opener = rpc[at:at + 700] if at >= 0 else ''
if not opener:
    failures.append('the XML-RPC open entry point is gone')
else:
    closing = opener.find('closeAllWindows')
    if closing < 0:
        failures.append('the XML-RPC open path no longer offers to close the open viewers')
    else:
        guard = opener[:closing]
        if 'CloseAllWindowsBeforeXMLRPCOpen' not in guard:
            failures.append('the XML-RPC open path closes every viewer without asking the '
                            'CloseAllWindowsBeforeXMLRPCOpen preference, so several series can no '
                            'longer be opened from a script')

defaults = (root / 'Horos/Sources/DefaultsOsiriX.m').read_bytes().decode('latin1')
if 'CloseAllWindowsBeforeXMLRPCOpen' not in defaults:
    failures.append('the preference has no registered default, so its meaning depends on whether '
                    'the user has ever seen the Listener pane')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: window tabbing is refused at start-up, opening a series asks for its own viewer, and '
      'the XML-RPC path still consults the preference that closes the others')
