#!/usr/bin/env python3
"""Nothing raises a modal panel from inside `applicationDidFinishLaunching:`.

"It hangs on startup" covers several different things, and they are told apart by
one question - what is the main thread's stack right now.
`tools/probe-startup-blocking.py` asks it once a second and prints the answer, so
each report can be given a cause instead of a guess.

The first thing it found: with the DICOM listener off and the Query/Retrieve
window open at quit, the main thread sat here for as long as it was watched -

    main -> applicationDidFinishLaunching: -> initAutoQuery: (QueryController.mm:4898)
         -> NSRunCriticalAlertPanel -> runModalForWindow:

- because `-applicationDidFinishLaunching:` builds that window, and building it
  raised a critical panel about the listener. The launch does not finish while a
modal panel is up, and the statement right after the one that raised it is
`[[QueryController currentQueryController] showWindow: self]`, so the panel
appeared with no Q&R window behind it to explain what it was about.

Raised on the next turn of the run loop instead, the stack becomes

    main -> __33-[QueryController initAutoQuery:]_block_invoke -> NSRunCriticalAlertPanel

with `applicationDidFinishLaunching:` gone from it, and the windows are on screen:
`get name of every window` answers "DICOM Query/Retrieve, ..., db DB, ...".
"""
from pathlib import Path
import ast
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
query = (root / 'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')
probe = root / 'tools/probe-startup-blocking.py'


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


# --- the listener panel does not hold up the launch ---------------------------
region = body('- (id) initAutoQuery:', query) or body('-(id)initAutoQuery:', query)
if not region:
    failures.append('-initAutoQuery: is gone')
else:
    live = re.sub(r'//[^\n]*', '', region)
    panels = [m.start() for m in re.finditer(r'NSRun\w*AlertPanel', live)]
    if len(panels) < 2:
        failures.append('one of the two warnings this window raises is gone: no DICOM locations, '
                        'and the listener not running')
    for at in panels:
        before = live[max(0, at - 300):at]
        if 'dispatch_async( dispatch_get_main_queue()' not in before:
            failures.append('a warning is still raised inline, so a window built during '
                            'applicationDidFinishLaunching: stops the launch on a modal panel')
            break
    if 'listenerRequiredForServers' not in live:
        failures.append('the warning no longer asks whether any node actually needs the listener')

# --- and the probe that says so is here ---------------------------------------
if not probe.exists():
    failures.append('the tool that samples the main thread during startup is gone')
else:
    text = probe.read_text()
    try:
        ast.parse(text)
    except SyntaxError as error:
        failures.append('the probe does not parse: %s' % error)
    for needed in ('sample', 'com.apple.main-thread'):
        if needed not in text:
            failures.append('the probe does not read the main thread from sample(1): %r missing'
                            % needed)
    if 'interval' not in text:
        failures.append('the probe takes a single sample, so it cannot tell a block from work')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the listener warning waits for the launch to finish, and the main thread can be '
      'sampled while an application starts')
