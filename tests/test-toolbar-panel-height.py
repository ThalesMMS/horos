#!/usr/bin/env python3
"""The toolbar panel is as tall as its toolbar, not as tall as a number from 2009.

When the 2D viewer's toolbar is detached into its own panel across the top of the
screen, two constants decided the geometry:

    static int fixedHeight = 100;                                  // ToolbarPanel.m
    screenFrame.size.height -= 78;  //[[AppController toolbarFor…] // AppController.m

78 is 100 minus a 22-point menu bar, frozen in place beside the expression it
replaced. Both halves have moved since. The toolbar draws an icon and a label in
the expanded style at the current system font, and on macOS 26 that needs more
than a hundred points: the panel's `contentLayoutRect` came back **zero points
tall**, which is AppKit saying the title bar and the toolbar had already taken
everything the window had. What did not fit was the bottom of the labels - a
capture of the panel had lit pixels on its very last row, the descenders of
"Cloud Report" and "Key Image" cut against the windows tiled underneath.

So the panel asks AppKit what its chrome takes, keeps 100 only as a floor, and
the tiling subtracts what the panel actually reserves instead of 78.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


panel = (root / 'Horos/Sources/ToolbarPanel.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/ToolbarPanel.h').read_bytes().decode('latin1')
application = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
code = strip(panel)

if '+ (long) heightForPanelWindow: (NSWindow*) window;' not in header:
    failures.append('the panel does not offer to measure a window, so nothing can ask AppKit '
                    'what the toolbar takes')

at = code.find('+ (long) heightForPanelWindow:')
body = code[at:code.index('\n}', at) + 2] if at >= 0 else ''
if not body:
    failures.append('heightForPanelWindow: is gone')
elif 'frameRectForContentRect' not in body:
    failures.append('the height is not asked of AppKit, so it cannot follow the toolbar style, '
                    'the system font or the labels')

at = code.find('- (long) fixedHeight')
body = code[at:code.index('\n}', at) + 2] if at >= 0 else ''
if not body:
    failures.append('fixedHeight is gone')
else:
    if 'heightForPanelWindow' not in body:
        failures.append('fixedHeight answers without measuring, so the panel is whatever the '
                        'constant says and the labels are cut again')
    if re.search(r'return\s+fixedHeight\s*;', body):
        failures.append('fixedHeight still returns the constant')

# The floor has to stay: a window that cannot be measured must not shrink the panel.
at = code.find('+ (long) panelHeight')
body = code[at:code.index('\n}', at) + 2] if at >= 0 else ''
if not body or 'fixedHeight' not in body:
    failures.append('nothing keeps the historical 100 as a floor, so an unmeasurable window '
                    'would give a panel of no height at all')

for which in ('- (long) exposedHeight', '+ (long) exposedHeight'):
    at = code.find(which)
    body = code[at:code.index('\n}', at) + 2] if at >= 0 else ''
    if not body:
        failures.append('%s is gone' % which)
    elif 'panelHeight' not in body and 'ToolbarPanelController exposedHeight' not in body:
        failures.append('%s still computes from the constant, so the room left for the viewers '
                        'does not follow the panel' % which)

if '- (void) toolbarDidChange:' not in panel and '- (void) toolbarDidChange: (NSNotification*)' not in panel:
    failures.append('customizing the toolbar does not remasure the panel')

# And the tiling takes its number from the panel rather than from 78.
at = application.find('+ (NSRect) usefullRectForScreen: (NSScreen*) screen showFloatingWindows:')
useful = application[at:at + 1400] if at >= 0 else ''
if not useful:
    failures.append('usefullRectForScreen:showFloatingWindows: is gone')
else:
    if re.search(r'screenFrame\.size\.height\s*-=\s*\d', useful):
        failures.append('the tiling still subtracts a literal height for the toolbar panel, so '
                        'the two numbers drift apart and the windows cover the labels')
    if 'ToolbarPanelController exposedHeight' not in useful:
        failures.append('the tiling does not ask the panel how much room it takes')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the panel measures its own toolbar, keeps 100 only as a floor, and the tiling leaves '
      'room by asking the panel')
