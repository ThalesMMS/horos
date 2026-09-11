#!/usr/bin/env python3
"""The RC attachment is a volume-discovery hang, not checkEverythingLoaded (#282).

horosproject/horos#277 attached a machine spindump, not an exception report.
The audit line ViewerController.m:2321 / checkEverythingLoaded is not in that
file. This test keeps the reading attached to the selectors the spindump
actually printed, and refuses to mix the NSAlert front (#277) or the 3.1.2
hangs (#279).
"""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
failures = []

# Redacted public stacks only. The full spindump stays off-git (other processes,
# hardware identifiers). Source: horosproject/horos/files/1755707/Horos.Spindump.txt
EXCERPT = """
Date/Time: 2018-02-24 21:40:09 -0600
OS Version: Mac OS X 10.12.6 (Build 16G1212)
Architecture: x86_64h
Command: Horos
Version: 3.0.0 (20180220)
Hardware model: iMac14,2
Duration: 10.01s (process was unresponsive for 51854 seconds before sampling)
 1001 -[BrowserSourcesHelper _observeVolumeNotification:] + 270 (Horos + 8115710)
 1001 -[BrowserSourcesHelper _analyzeVolumeAtPath:] + 693 (Horos + 8114405)
 1001 +[NSThread sleepForTimeInterval:]
 1001 -[AppController startSTORESCP:] + 519
 1001 DcmQueryRetrieveSCP::waitForAssociation(T_ASC_Network*)
"""


def body(path, signature):
    source = path.read_bytes().decode('latin1')
    start = 0
    while True:
        at = source.find(signature, start)
        if at < 0:
            return ''
        after = source[at + len(signature):].lstrip()
        if after.startswith('{'):
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
        start = at + 1


def check(condition, message):
    if not condition:
        failures.append(message)


# --- the attachment is one volume hang, not a crash or the 3.1.2 pair --------
check(EXCERPT.count('Version: 3.0.0') == 1, 'the excerpt must stay on Horos 3.0.0 RC')
check('20180220' in EXCERPT, 'the RC build date must stay as printed')
check('x86_64h' in EXCERPT, 'architecture must stay Intel as printed')
check('iMac14,2' in EXCERPT, 'the late-2013 iMac model must stay as printed')
check('51854 seconds' in EXCERPT, 'the 14-hour unresponsive interval must stay')
check('Exception Type:' not in EXCERPT, 'do not relabel the spindump as a crash')
check('checkEverythingLoaded' not in EXCERPT,
      'the audit ViewerController frame is not in the attachment')
check('windowWillClose:' not in EXCERPT and '3.1.2' not in EXCERPT,
      'this log is not the #279 3.1.2 pair')
check('NSAlert' not in EXCERPT and 'NSRunAlertPanel' not in EXCERPT,
      'this log is not the #277 NSAlert stack')
check('_analyzeVolumeAtPath:' in EXCERPT and '_observeVolumeNotification:' in EXCERPT,
      'the volume-discovery hang signature must remain identifiable')
check('startSTORESCP:' in EXCERPT, 'the idle Store-SCP frame must stay named')
check('getDicomField:forFile:' not in EXCERPT and 'Load Image Data' not in EXCERPT,
      'do not import the #116 / #279 worker lock into this excerpt')

# --- those selectors still exist, and the main-thread sleep is gone ----------
sources = root / 'Horos/Sources/BrowserController+Sources.m'
analyze = body(sources, '-(void)_analyzeVolumeAtPath:(NSString*)path')
observe = body(sources, '-(void)_observeVolumeNotification:(NSNotification*)notification')
orientation = body(root / 'Horos/Sources/ViewerController.m',
                   '- (BOOL) setOrientation: (int) newOrientationTool')
loaded = body(root / 'Horos/Sources/ViewerController.m',
              '-(void) checkEverythingLoaded')
discovery = (root / 'Horos/Sources/HorosVolumeDiscovery.h').read_bytes().decode('latin1')
bounded = (root / 'Horos/Sources/HorosBoundedTask.h').read_bytes().decode('latin1')

check(analyze and 'discoverPath:' in analyze and 'HorosRunBoundedTask' in analyze,
      '_analyzeVolumeAtPath: must still hand diskutil to bounded discovery')
check(analyze and 'sleepForTimeInterval' not in analyze,
      '_analyzeVolumeAtPath: grew a main-thread sleep; that is the RC hang')
check(observe and '_analyzeVolumeAtPath:' in observe,
      'the notification observer must still reach volume analysis')
check(observe and 'sleepForTimeInterval' not in observe,
      '_observeVolumeNotification: must not sleep on the main thread')
check('addOperationWithBlock' in discovery,
      'HorosVolumeDiscovery must still run the worker off the main thread')
check('HorosRunBoundedTask' in bounded and 'timeout' in bounded,
      'the diskutil helper must still have a deadline')
check(loaded and 'sleepForTimeInterval' in loaded,
      'checkEverythingLoaded still exists; do not pretend this issue removed it')
check(orientation and 'checkEverythingLoaded' in orientation,
      'the audit line lives in setOrientation:, which the attachment never names')
check('checkEverythingLoaded' not in analyze and 'checkEverythingLoaded' not in observe,
      'do not route the RC hang through ViewerController')

# #277 stays on another front: volume analysis is not alert teardown.
alert = re.compile(r'NSAlert|NSRun\w*AlertPanel')
check(not alert.search(analyze), '_analyzeVolumeAtPath: grew an alert; do not fold #277 into #282')
check(not alert.search(observe), '_observeVolumeNotification: grew an alert; do not fold #277 into #282')

if failures:
    for item in failures:
        print('FAIL:', item)
    sys.exit(1)
print('ok: RC attachment is a volume hang; checkEverythingLoaded/#277/#279 stay rejected')
