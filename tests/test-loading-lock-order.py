#!/usr/bin/env python3
"""Nothing waits for a worker while holding a lock that worker needs.

The report behind issue #116 is a spindump: the main thread waiting for images to
load, worker threads stopped in `getDicomField` on a lock the main thread held.
That shape - hold a lock, then wait for somebody who needs it - is a deadlock
whenever the two halves are true at once, and no amount of running proves it
absent, because it depends on timing.

So the property is checked in the source instead. Every region between
`[<name>Lock lock]` and its `unlock` that waits for other threads is found, the
work it waits for is followed to its implementation, and the region fails if that
work takes the same lock. Horos has eleven such regions today and all of them are
safe; a twelfth that is not would fail here.

The other half is about the wait itself: `-[ViewerController checkEverythingLoaded]`
spins on the main thread until the loading thread finishes, and it must never be
reached from inside a lock region, because everything the loading thread does is
then behind that lock.

The measured side of the same issue - how long those locks are really held, and
by whom - is `tools/probe-lock-order.m` and `docs/loading-locks.md`; a static
rule cannot say anything about that, and a run cannot say anything about this.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []

WAITS = {
    'sleepForTimeInterval': 'sleeps until another thread finishes',
    'waitUntilAllOperationsAreFinished': 'waits for an operation queue',
    'waitUntilFinished': 'waits for a thread or operation',
    'waitUntilDone: YES': 'waits for the main thread',
    'waitUntilDone:YES': 'waits for the main thread',
    'checkEverythingLoaded': 'waits for the loading thread',
    'runModal': 'runs a modal loop',
}
LOCK = re.compile(r'\[\s*(\w*[Ll]ock)\s+lock\s*\]')
UNLOCK = re.compile(r'\[\s*(\w*[Ll]ock)\s+unlock(?:WithCondition:)?')
SELECTOR = re.compile(r'@selector\(\s*([A-Za-z_]\w*:?)')
# Work is also handed over as an NSOperation rather than a selector, and then the
# body to follow is that class's -main.
OPERATION = re.compile(r'\[\s*\[\s*(\w+)\s+alloc\s*\]')

sources = sorted(list((root / 'Horos/Sources').glob('*.m')) +
                 list((root / 'Horos/Sources').glob('*.mm')))
bodies = {path: path.read_bytes().decode('latin1') for path in sources}


def mainOf(className):
    """The -main of that class, which is what an operation queue runs."""
    for path, text in bodies.items():
        at = text.find('@implementation %s\n' % className)
        if at < 0:
            at = text.find('@implementation %s ' % className)
        if at < 0:
            continue
        body = text[at:text.find('\n@end', at) if '\n@end' in text[at:] else at + 20000]
        found = re.search(r'^-\s*\(\s*void\s*\)\s*main\b', body, re.M)
        if not found:
            return None
        rest = body[found.start():]
        end = re.search(r'\n[-+]\s*\(', rest[1:])
        return rest[:end.start() + 1] if end else rest
    return None


def implementation(selector):
    """The body of the method with that selector, wherever it is defined."""
    name = selector.rstrip(':')
    pattern = re.compile(r'^[-+]\s*\([^)]*\)\s*%s[:\s]' % re.escape(name), re.M)
    for path, text in bodies.items():
        found = pattern.search(text)
        if not found:
            continue
        rest = text[found.start():]
        # To the next method at column zero, which is close enough to its end.
        end = re.search(r'\n[-+]\s*\(', rest[1:])
        return rest[:end.start() + 1] if end else rest[:8000]
    return None


regions = []
for path, text in bodies.items():
    open_regions = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = re.sub(r'//.*', '', line)
        for body in open_regions.values():
            body[1].append(stripped)
        for match in LOCK.finditer(stripped):
            open_regions.setdefault(match.group(1), (number, []))
        for match in UNLOCK.finditer(stripped):
            name = match.group(1)
            if name in open_regions:
                start, body = open_regions.pop(name)
                if number - start > 1:
                    regions.append((path.name, name, start, number, '\n'.join(body)))

waiting = []
for name, lock, start, end, body in regions:
    reasons = sorted({why for wait, why in WAITS.items() if wait in body})
    if reasons:
        waiting.append((name, lock, start, end, body, reasons))

if not waiting:
    failures.append('no region holds a lock across a wait any more, which is either very good '
                    'news or a sign this test stopped looking')

for name, lock, start, end, body, reasons in waiting:
    # The work being waited for: whatever selectors the region hands to other
    # threads. If any of them takes this very lock, the wait cannot end.
    # The lock is not always named directly: `[[ctrl roiLock] lock]` and
    # `[self.mainDatabase processFilesLock]` reach it through an accessor, and an
    # ivar spelt `_processFilesLock` is read back as `processFilesLock`. Match the
    # name wherever it appears, as long as a blocking `lock` follows it closely.
    # `tryLock` is left out on purpose: it does not wait, so it cannot deadlock.
    takesTheLock = re.compile(r'\b%s\b[^;]{0,60}?\block(?:WhenCondition)?\s*[\]:]'
                              % re.escape(lock.lstrip('_')))
    for selector in sorted(set(SELECTOR.findall(body))):
        worker = implementation(selector)
        if worker and takesTheLock.search(worker):
            failures.append('%s:%d holds %s and waits for %s, which takes %s itself'
                            % (name, start, lock, selector, lock))
    for className in sorted(set(OPERATION.findall(body))):
        worker = mainOf(className)
        if worker and takesTheLock.search(worker):
            failures.append('%s:%d holds %s and waits for %s, whose -main takes %s itself'
                            % (name, start, lock, className, lock))

# The loading wait in particular: it spins the main thread until the loading
# thread is done, so a lock held around it is held for a whole series load.
for name, lock, start, end, body, reasons in waiting:
    if 'checkEverythingLoaded' in body:
        failures.append('%s:%d holds %s across -[ViewerController checkEverythingLoaded], which '
                        'waits for the loading thread' % (name, start, lock))

# And it has to still be the spin it is described as, or the paragraph above is
# about something that no longer exists.
viewer = bodies[root / 'Horos/Sources/ViewerController.m']
at = viewer.find('-(void) checkEverythingLoaded')
loop = viewer[at:at + 1800] if at >= 0 else ''
if not loop:
    failures.append('checkEverythingLoaded is gone')
elif 'sleepForTimeInterval' not in loop or 'loadingThread.isExecuting' not in loop:
    failures.append('checkEverythingLoaded no longer waits on the loading thread the way this '
                    'test assumes')

for failure in failures:
    print('FAIL: %s' % failure)
print('%d region(s) hold a lock across a wait; none waits for work that needs that lock'
      % len(waiting))
for name, lock, start, end, body, reasons in sorted(waiting):
    print('  %-30s %-32s %5d-%-5d %s' % (name, lock, start, end, ', '.join(reasons)))

if failures:
    sys.exit(1)
print('ok: no lock is held across a wait for work that needs it')
