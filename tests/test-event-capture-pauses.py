#!/usr/bin/env python3
"""Classify 1–2 s input gaps without presuming a Horos cause (#286).

The 2017 report (horosproject/horos#194) described 1–2 s stretches where
brush, database scrolling and image scrolling all stopped registering
events. This test keeps three things distinct: a gap with a live main
heartbeat (events absent), a gap where the heartbeat also stalled (main
blocked), and the database click-hold / thumbnail hold-to-drag timeouts,
which are not a drawing stall. It compiles the production classifier,
pumps a host run-loop with a draw tick, a heartbeat and background work,
and checks the three event surfaces still match those contracts.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
helper = root / 'Horos/Sources/EventCapturePause.swift'
project = (root / 'Horos.xcodeproj/project.pbxproj').read_bytes().decode('latin1')
failures = []


def body(path, signature):
    source = path.read_bytes().decode('latin1')
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


def check(condition, message):
    if not condition:
        failures.append(message)


if not helper.is_file():
    failures.append('Horos/Sources/EventCapturePause.swift is missing')
check('EventCapturePause.swift' in project,
      'project.pbxproj does not compile EventCapturePause.swift')

viewer_drag = body(root / 'Horos/Sources/DCMView.m',
                   '- (void)mouseDragged:(NSEvent *)event')
image_scroll = body(root / 'Horos/Sources/DCMView.m',
                    '- (void)mouseDraggedImageScroll:(NSEvent *)event')
viewer_wheel = body(root / 'Horos/Sources/DCMView.m',
                    '- (void)scrollWheel:(NSEvent *)theEvent')
database_wheel = body(root / 'Horos/Sources/BrowserController.m',
                      '- (void)scrollWheel: (NSEvent *)theEvent')
matrix_down = body(root / 'Horos/Sources/BrowserMatrix.m',
                   '- (void) mouseDown:(NSEvent *)event')
thumb_down = body(root / 'Horos/Sources/O2ViewerThumbnailsMatrix.mm',
                  '- (void)mouseDown:(NSEvent*)event')

for name, method in (
        ('DCMView mouseDragged', viewer_drag),
        ('DCMView mouseDraggedImageScroll', image_scroll),
        ('DCMView scrollWheel', viewer_wheel),
        ('BrowserController scrollWheel', database_wheel)):
    check(method, '%s is gone' % name)
    check('nextEventMatchingMask' not in method,
          '%s nested a tracking run-loop' % name)
    check('startPeriodicEvents' not in method,
          '%s started periodic events' % name)
    check('sleepForTimeInterval' not in method and 'usleep' not in method,
          '%s sleeps on the event path' % name)
    check('waitUntilDone:YES' not in method,
          '%s waits synchronously on the event path' % name)

check(viewer_drag and 'setNeedsDisplay:YES' in viewer_drag,
      'viewer drag no longer asks for a display pass')
check(viewer_drag and 'mouseDraggedForROIs' in viewer_drag
      and 'checkROIsForHitAtPoint' in viewer_drag,
      'brush / ROI drag left the mouseDragged path')
check(image_scroll and 'HorosScrollDirection' in image_scroll,
      'image-scroll drag left the shared direction helper')
check(database_wheel and 'previewSliderAction' in database_wheel,
      'database wheel no longer advances the preview slider')

check(matrix_down and 'startPeriodicEventsAfterDelay: 0 withPeriod:0.001' in matrix_down,
      'database matrix lost its click-hold periodic pump')
check(matrix_down and '[start timeIntervalSinceNow] >= -1' in matrix_down,
      'database matrix click-hold is no longer one second')
check(matrix_down and 'startDrag:' in matrix_down,
      'database matrix click-hold no longer starts a drag')
check(thumb_down and 'DRAGTIMEOUT -2' in thumb_down,
      'thumbnail hold-to-drag timeout left O2ViewerThumbnailsMatrix')
check(thumb_down and 'nextEventMatchingMask' in thumb_down,
      'thumbnail mouseDown lost its tracking pump')

# A 1 s / 2 s hold-to-drag is not the reported 1–2 s stall during drawing.
check(matrix_down and 'mouseRoiDragged' not in matrix_down,
      'do not treat the database click-hold as the brush path')

if helper.is_file():
    driver = r'''
import AppKit

precondition(EventCapturePause.historicalPauseMinimum == 1.0)
precondition(EventCapturePause.historicalPauseMaximum == 2.0)
precondition(EventCapturePause.databaseClickHoldLimit == 1.0)
precondition(EventCapturePause.thumbnailHoldToDragLimit == 2.0)

precondition(EventCapturePause.classify(eventGap: 0.02, heartbeatGap: 0.02) == .withinCadence)
precondition(EventCapturePause.classify(eventGap: 0.9, heartbeatGap: 0.02) == .withinCadence)
precondition(EventCapturePause.classify(eventGap: 1.5, heartbeatGap: 0.02) == .eventAbsence,
             "a 1.5 s event hole with a live heartbeat is absence, not a main-thread stall")
precondition(EventCapturePause.classify(eventGap: 1.5, heartbeatGap: 1.4) == .mainBlocked,
             "when the heartbeat also stops, do not call it a silent event hole")
precondition(EventCapturePause.classify(eventGap: 2.0, heartbeatGap: 2.0) == .mainBlocked)

precondition(EventCapturePause.largestGap(in: [10.0, 10.02, 10.05]) < 0.04)
precondition(abs(EventCapturePause.largestGap(in: [1.0, 1.02, 2.62]) - 1.6) < 0.0001)
precondition(EventCapturePause.largestGap(in: [3.0]) == 0)

let sample = EventCapturePause.measureHostRunLoop(duration: 4.2)
precondition(sample.drawTicks >= 200, "draw ticks too few: \(sample.drawTicks)")
precondition(sample.heartbeatTicks >= 200, "heartbeat ticks too few: \(sample.heartbeatTicks)")
precondition(sample.maxDrawGap < EventCapturePause.historicalPauseMinimum,
             "host draw gap \(sample.maxDrawGap) reached the historical pause")
precondition(sample.maxHeartbeatGap < EventCapturePause.historicalPauseMinimum,
             "host heartbeat gap \(sample.maxHeartbeatGap) looks like a main-thread stall")
precondition(sample.kind == .withinCadence,
             "host run-loop classified \(sample.kind.rawValue) instead of withinCadence")
precondition(sample.backgroundIterations > 0, "coexisting work never ran")

print("PASS: host arm64 draw=\(sample.drawTicks) beat=\(sample.heartbeatTicks) "
      + "maxDraw=\(String(format: "%.4f", sample.maxDrawGap)) "
      + "maxBeat=\(String(format: "%.4f", sample.maxHeartbeatGap)) "
      + "background=\(sample.backgroundIterations) duration=\(String(format: "%.3f", sample.duration))")
'''
    with tempfile.TemporaryDirectory(prefix='horos-event-capture-') as directory:
        main = Path(directory) / 'main.swift'
        main.write_text(driver)
        binary = Path(directory) / 'event-capture'
        built = subprocess.run(
            ['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
             str(helper), str(main)],
            capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('EventCapturePause.swift does not compile:\n%s'
                            % (built.stderr or built.stdout)[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            sys.stdout.write(run.stdout)
            probe = run.stdout + run.stderr
            if run.returncode != 0 and 'draw ticks too few' in probe:
                # The host half counts real display refreshes. A machine with no
                # window server session has none, so there is nothing to count
                # and nothing is learned about the cadence. The classification
                # half above ran and is not affected.
                for failure in failures:
                    print('FAIL:', failure)
                if failures:
                    sys.exit(1)
                print('skipped: the host run-loop half needs a display that '
                      'refreshes; this machine produced too few draw ticks',
                      file=sys.stderr)
                sys.exit(2)
            if run.returncode != 0:
                failures.append('event-capture probe failed: %s %s'
                                % (run.stdout[-400:], run.stderr[-800:]))
            elif 'PASS:' not in run.stdout:
                failures.append('event-capture probe printed nothing useful: %r'
                                % run.stdout)

for failure in failures:
    print('FAIL:', failure)
if failures:
    sys.exit(1)
print('ok: 1-2s event gaps classify as absence or main-blocked; host arm64 '
      'run-loop stayed within cadence; brush/scroll stay event-driven; '
      'database 1s/2s holds stay click-to-drag')
