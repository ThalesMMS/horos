#!/usr/bin/env python3
"""A destination that is down does not fill the screen with alerts.

Every failed send raised a modal alert on the main thread. A destination that is
down fails every batch, so a queue of forty batches was forty alerts to dismiss
before the application could be used again - which is what "the interface froze
while routing" turns out to be from the user's side.

The first failure of a destination is now shown and the repeats are logged. The
gate is Swift and is compiled and run here; the send that uses it is checked in
source. The load itself is tools/measure-routing-load.sh; see the validation
document for what it measured.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
gate = root / 'Horos/Sources/RoutingDestination.swift'
routing = (root / 'Horos/Sources/DicomDatabase+Routing.mm').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print(key + "\t" + value) }
func yn(_ value: Bool) -> String { return value ? "yes" : "no" }

let down = "PACSB@127.0.0.1:11182"
emit("first", yn(SuspendedRoutingRules.shouldReport(problem: "refused", forDestination: down)))
emit("again", yn(SuspendedRoutingRules.shouldReport(problem: "refused", forDestination: down)))
emit("third", yn(SuspendedRoutingRules.shouldReport(problem: "refused", forDestination: down)))
// A different failure of the same destination is news.
emit("different", yn(SuspendedRoutingRules.shouldReport(problem: "timed out", forDestination: down)))
// Another destination is not silenced by the first.
emit("other", yn(SuspendedRoutingRules.shouldReport(problem: "refused",
                                                    forDestination: "PACSA@127.0.0.1:11181")))
// It answered, so the next failure is news again.
SuspendedRoutingRules.clearProblems(forDestination: down)
emit("afterSuccess", yn(SuspendedRoutingRules.shouldReport(problem: "refused", forDestination: down)))
// And a rule name cannot silence a destination that happens to share it.
SuspendedRoutingRules.resumeAll()
_ = SuspendedRoutingRules.suspend(rule: down, because: "refused")
emit("noCollision", yn(SuspendedRoutingRules.shouldReport(problem: "refused", forDestination: down)))
'''

results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-load-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'gate'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(gate), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the gate does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the gate driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {'first': 'yes', 'again': 'no', 'third': 'no', 'different': 'yes',
                'other': 'yes', 'afterSuccess': 'yes', 'noCollision': 'yes'}
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))

# --- the send ------------------------------------------------------------------
at = routing.find('-(void)_routingExecuteSend:')
body = routing[at:at + 3000] if at >= 0 else ''
if not body:
    failures.append('-_routingExecuteSend: is gone')
else:
    if 'shouldReportProblem:' not in body:
        failures.append('every failure still raises an alert')
    if 'clearProblemsForDestination:' not in body:
        failures.append('a destination that answers again never reports its next failure')
    # The alert must be gated, not merely logged beside the gate.
    gated = re.search(r'if\(\s*\[HorosSuspendedRoutingRules shouldReportProblem:[^\n]*\)\s*\n\s*'
                      r'\[self performSelectorOnMainThread:@selector\(_routingErrorMessage:\)', body)
    if not gated:
        failures.append('the alert is not the thing the gate controls')
    if 'Autorouting FAILED' not in body:
        failures.append('a failed send is no longer logged')

# The report is logged whether or not it is shown, so a run can be counted.
alert = routing[routing.find('-(void)_routingErrorMessage:'):]
alert = alert[:alert.find('\n}')]
logged = alert.find('NSLog')
suppressed = alert.find('ShowErrorMessagesForAutorouting')
if logged < 0 or suppressed < 0 or logged > suppressed:
    failures.append('an alert that is suppressed leaves no trace, so alerts cannot be counted')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a destination that keeps failing is reported once, another destination is not '
      'silenced with it, and one that answers again reports its next failure')
