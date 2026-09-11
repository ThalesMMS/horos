#!/usr/bin/env python3
"""#374/A224: the 4D play control says what is actually happening.

A224 asks for a play control that is *visible, accessible and operating* on a
series with at least three times, and in a *coherent* off/absent state on a
static 3D series.

Two things were not coherent.

`-MovieStop:` stopped the timer without touching the button, so every way of
stopping other than pressing it — opening a 3D viewer, or another viewer
starting to play — left this one reading "Stop" with nothing playing.

And loading a series reset `maxMovieIndex` to 1 and switched the control off
**without stopping the movie**. The timer went on firing
`-performMovieAnimation:` behind a disabled button that still said "Stop": the
images kept changing and the control that would stop them could not be pressed.

The control is a nib outlet driven by mouse events, so this checks the rule it
now follows and the places that ask for it.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

source = root / 'Horos/Sources/FourDSeriesGuard.swift'
if not source.is_file():
    failures.append('Horos/Sources/FourDSeriesGuard.swift is missing')
else:
    driver = r'''
import Foundation

@main struct Check {
    static func main() {
        typealias G = FourDSeriesGuard

        // A static 3D series has one time: nothing to play through.
        precondition(!G.playControlApplies(timeCount: 1))
        precondition(!G.playControlApplies(timeCount: 0))
        precondition(!G.playControlApplies(timeCount: -3))
        // Two is already a movie; the criterion's case is three.
        precondition(G.playControlApplies(timeCount: 2))
        precondition(G.playControlApplies(timeCount: 3))
        precondition(G.playControlApplies(timeCount: G.timeCapacity))

        // Coherence: a movie running behind a switched-off control is the state
        // A224 refuses. Everything else is fine.
        precondition(!G.playControlIsCoherent(enabled: false, playing: true))
        precondition(G.playControlIsCoherent(enabled: false, playing: false))
        precondition(G.playControlIsCoherent(enabled: true, playing: true))
        precondition(G.playControlIsCoherent(enabled: true, playing: false))

        // And the two agree: on a static series the control is off, so nothing
        // may be playing.
        for times in [0, 1, 2, 3, 17] {
            let enabled = G.playControlApplies(timeCount: times)
            precondition(G.playControlIsCoherent(enabled: enabled, playing: enabled))
        }
        print("rule ok")
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='horos-4d-play-') as folder:
        path = Path(folder)
        (path / 'Check.swift').write_text(driver)
        build = subprocess.run(['xcrun', 'swiftc', '-parse-as-library', str(source),
                                str(path / 'Check.swift'), '-o', str(path / 'check')],
                               capture_output=True, text=True)
        if build.returncode:
            failures.append('the guard does not compile: %s' % build.stderr.strip().splitlines()[-3:])
        else:
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            if run.returncode:
                failures.append('the guard does not answer as A224 needs: %s' % run.stderr.strip())

viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')

stop = re.search(r'- \(void\) MovieStop:\(id\) sender\s*\{(.*?)\n\}', viewer, re.S)
if not stop:
    failures.append('-MovieStop: is gone')
else:
    if 'movieTimer invalidate' not in stop.group(1):
        failures.append('-MovieStop: no longer stops the timer')
    if 'moviePlayStop setTitle' not in stop.group(1):
        failures.append('-MovieStop: must put the control back to "Play"; stopping any other way '
                        'left it reading "Stop" with nothing playing')

toggle = re.search(r'- \(void\) MoviePlayStop:\(id\) sender\s*\{(.*?)\n\}\n\n', viewer, re.S)
if not toggle:
    failures.append('-MoviePlayStop: is gone')
else:
    if '[self MovieStop: self]' not in toggle.group(1):
        failures.append('-MoviePlayStop: must stop through -MovieStop:, not with its own copy')
    if 'movieTimer invalidate' in toggle.group(1):
        failures.append('-MoviePlayStop: still has its own copy of the stop')
    if 'scheduledTimerWithTimeInterval' not in toggle.group(1):
        failures.append('-MoviePlayStop: no longer starts the movie')

# The series-load path resets maxMovieIndex to 1 and switches the control off;
# it must stop the movie first.
if 'playControlAppliesWithTimeCount' not in viewer:
    failures.append('the series-load path must ask HorosFourDSeriesGuard whether the control applies')
else:
    ask = viewer.find('playControlAppliesWithTimeCount')
    disable = viewer.find('[moviePlayStop setEnabled:NO]')
    if disable < 0 or not ask < disable:
        failures.append('the movie must be stopped before the control is switched off')
    window = viewer[ask:disable]
    if 'MovieStop' not in window:
        failures.append('the series-load path must stop the movie when the new series has one time')

# A224 says visible, accessible and operating. The control it is about had no
# accessibility label, while both of its neighbours did.
for outlet, what in (('moviePlayStop', 'the play control'), ('moviePosSlider', 'the phase slider')):
    if not re.search(r'\[%s setAccessibilityLabel' % outlet, viewer):
        failures.append('%s has no accessibility label' % what)
    if not re.search(r'\[%s setAccessibilityHelp' % outlet, viewer):
        failures.append('%s has no accessibility help' % what)

# And the animation must keep asking the guard for the next index: this is the
# #220 buffer safety, which A224 says not to confuse with the control.
if 'HorosFourDSeriesGuard nextIndex' not in viewer:
    failures.append('-performMovieAnimation: no longer asks the guard for the next index')

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)

print('PASS: the 4D control is off for a single time, stops the movie before it is switched off, '
      'never reads "Stop" with nothing playing, and carries accessibility labels')
