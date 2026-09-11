#!/usr/bin/env python3
"""Each autorouting rule is applied once per trigger, and the log says why.

-applyRoutingRules:toImages: walked the rules and, for every activated one,
handed -__applyRoutingRules: the whole list. Two rules therefore applied every
rule twice; five applied every rule five times. A rule carrying a schedule did it
again when its delay elapsed, for every other rule too.

The send queue de-duplicates against what is currently queued, so the repeats
were invisible while the first copy was still there — and the routing timer
drains that queue every ten seconds, after which the same images are queued again
and sent again.

The partition is Swift and is compiled and run here. The logging that names the
trigger, the rule and the counts is checked in source.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
schedule = root / 'Horos/Sources/RoutingSchedule.swift'
routing = (root / 'Horos/Sources/DicomDatabase+Routing.mm').read_bytes().decode('latin1')
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
browser = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print(key + "\t" + value) }
func names(_ rules: [[String: Any]]) -> String {
    return rules.map { $0["name"] as? String ?? "?" }.joined(separator: ",")
}

let rules: [[String: Any]] = [
    ["name": "plain"],                                        // no keys at all
    ["name": "off", "activated": false],
    ["name": "on", "activated": true, "scheduleType": 0],
    ["name": "delayed", "activated": true, "scheduleType": 1, "delayTime": 2],
    ["name": "window", "activated": true, "scheduleType": 2,
     "fromTime": "Monday, 01 January 2001 08:00:00 GMT", "toTime": "Monday, 01 January 2001 18:00:00 GMT"],
    // A window with no times cannot be worked out; the routing runs it now.
    ["name": "windowless", "activated": true, "scheduleType": 2],
    // Something newer than this code knows about: run it rather than drop it.
    ["name": "unknown", "activated": true, "scheduleType": 9],
    ["name": "offString", "activated": "0"],
]

emit("immediate", names(RoutingSchedule.immediateRules(in: rules)))
emit("scheduled", names(RoutingSchedule.scheduledRules(in: rules)))
emit("counted", String(RoutingSchedule.immediateRules(in: rules).count
                       + RoutingSchedule.scheduledRules(in: rules).count))
emit("activatedByDefault", RoutingSchedule.isActivated(["name": "plain"]) ? "yes" : "no")
emit("activatedByString", RoutingSchedule.isActivated(["activated": "1"]) ? "yes" : "no")
emit("deactivatedByString", RoutingSchedule.isActivated(["activated": "0"]) ? "yes" : "no")
emit("typeMissing", String(RoutingSchedule.scheduleType(of: ["name": "plain"])))
emit("typeNumber", String(RoutingSchedule.scheduleType(of: ["scheduleType": 2])))
'''

# --- the partition, compiled and run -----------------------------------------
results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-schedule-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'schedule'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(schedule), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the schedule does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the schedule driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {
        'immediate': 'plain,on,windowless,unknown',
        'scheduled': 'delayed,window',
        # Six activated rules, each in exactly one of the two lists.
        'counted': '6',
        'activatedByDefault': 'yes', 'activatedByString': 'yes', 'deactivatedByString': 'no',
        'typeMissing': '0', 'typeNumber': '2',
    }
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))

# --- the loop that used to apply every rule once per rule --------------------
at = routing.find('-(void)applyRoutingRules:(NSArray*)autoroutingRules toImages:')
if at < 0:
    failures.append('applyRoutingRules:toImages: is gone')
else:
    opening = routing.index('{', at)
    depth, index, body = 0, opening, ''
    while index < len(routing):
        if routing[index] == '{':
            depth += 1
        elif routing[index] == '}':
            depth -= 1
            if depth == 0:
                body = routing[opening:index + 1]
                break
        index += 1
    applications = re.findall(r'__applyRoutingRules:\s*(\w+)', body)
    if 'autoroutingRules' in applications:
        failures.append('the whole rule list is applied again per rule')
    if applications.count('thisRule') != 2:
        failures.append('a scheduled rule does not apply only itself: %r' % applications)
    if 'immediate' not in applications:
        failures.append('the unscheduled rules are not applied together, once')
    if 'HorosRoutingSchedule scheduledRulesIn:' not in body:
        failures.append('the scheduled rules are not partitioned by the schedule')
    if 'HorosRoutingSchedule immediateRulesIn:' not in body:
        failures.append('the immediate rules are not partitioned by the schedule')

# --- the log identifies the trigger ------------------------------------------
if 'Autorouting trigger:' not in database:
    failures.append('an import does not say it triggered the routing')
if 're-read from disk' not in database:
    failures.append('an import does not distinguish a re-read from a new file')
if browser.count('Autorouting trigger:') != 2:
    failures.append('applying a rule by hand does not say so')
for expected, missing in (
        ('Autorouting rule \\"%@\\" -> %@: %d of %d image(s) matched',
         'the log does not say which rule matched which images'),
        ('already queued for it, not queued again',
         'the log does not say when images were left out as already queued'),
        ('list: rule \\"%@\\" -> %@, %d item(s)',
         'the queue does not name the rule each list belongs to')):
    if expected not in routing:
        failures.append(missing)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: every activated rule is applied exactly once per trigger, a scheduled one by itself '
      'when its time comes, and the log names the trigger, the rule and the counts')
