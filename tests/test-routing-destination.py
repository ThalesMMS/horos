#!/usr/bin/env python3
"""An autorouting rule that cannot say where a study goes does not send it.

A rule stores its destination as the node's display name, and the routing queue
looked it up by walking the stored nodes and taking the first activated one whose
name matched. Two nodes sharing a name therefore sent the study to whichever the
list happened to hold first, and reordering the list changed the answer; a
renamed or deleted node made the rule match nothing, and the files already queued
for it were dropped with one N2LogError line and nothing shown to anyone.

The resolver is Swift and is compiled and run here. The queue that uses it is
checked in source.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
resolver = root / 'Horos/Sources/RoutingDestination.swift'
routing = (root / 'Horos/Sources/DicomDatabase+Routing.mm').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) { print(key + "\t" + value) }

func node(_ name: String, _ port: String, activated: Any? = nil) -> [String: Any] {
    var server: [String: Any] = ["Description": name, "AETitle": "AE" + port,
                                 "Address": "127.0.0.1", "Port": port]
    if let activated = activated { server["Activated"] = activated }
    return server
}

// The ordinary case: one node of that name.
let one = [node("PACS", "104"), node("ARCHIVE", "105")]
let good = RoutingDestination.destination(named: "PACS", inServers: one, ruleName: "nightly")
emit("good.resolved", good.resolved ? "yes" : "no")
emit("good.port", (good.server?["Port"] as? String) ?? "none")
emit("good.problem", good.problem ?? "none")

// A node with no Activated key is activated, as it is everywhere else.
let implicit = [["Description": "PACS", "AETitle": "AE", "Address": "127.0.0.1", "Port": "104"]]
emit("implicit.resolved",
     RoutingDestination.destination(named: "PACS", inServers: implicit, ruleName: nil).resolved
     ? "yes" : "no")

// Two nodes called the same thing: sending to the first would be a guess.
let ambiguous = [node("PACS", "104"), node("PACS", "11112")]
let two = RoutingDestination.destination(named: "PACS", inServers: ambiguous, ruleName: "nightly")
emit("ambiguous.resolved", two.resolved ? "yes" : "no")
emit("ambiguous.permanent", two.isPermanent ? "yes" : "no")
emit("ambiguous.problem", two.problem ?? "none")

// Renamed or removed.
let missing = RoutingDestination.destination(named: "PACS", inServers: [node("ARCHIVE", "105")],
                                             ruleName: "nightly")
emit("missing.resolved", missing.resolved ? "yes" : "no")
emit("missing.problem", missing.problem ?? "none")

// There, but switched off.
let off = RoutingDestination.destination(named: "PACS", inServers: [node("PACS", "104", activated: false)],
                                         ruleName: "nightly")
emit("off.resolved", off.resolved ? "yes" : "no")
emit("off.problem", off.problem ?? "none")

// A rule with no destination at all.
emit("empty.problem",
     RoutingDestination.destination(named: "", inServers: one, ruleName: nil).problem ?? "none")

// The suspension remembers the first report and forgets it once fixed.
emit("suspend.first", SuspendedRoutingRules.suspend(rule: "nightly", because: "gone") ? "yes" : "no")
emit("suspend.again", SuspendedRoutingRules.suspend(rule: "nightly", because: "gone") ? "yes" : "no")
emit("suspend.changed", SuspendedRoutingRules.suspend(rule: "nightly", because: "ambiguous") ? "yes" : "no")
emit("suspend.problem", SuspendedRoutingRules.problem(forRule: "nightly") ?? "none")
SuspendedRoutingRules.resume(rule: "nightly")
emit("suspend.afterResume", SuspendedRoutingRules.problem(forRule: "nightly") ?? "none")
emit("suspend.reportsAgain", SuspendedRoutingRules.suspend(rule: "nightly", because: "gone") ? "yes" : "no")
'''

# --- the resolver, compiled and run ------------------------------------------
results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-routing-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'routing'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(resolver), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the resolver does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the resolver driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    expected = {
        'good.resolved': 'yes', 'good.port': '104', 'good.problem': 'none',
        'implicit.resolved': 'yes',
        # Two of the same name: nothing is sent, and asking again will not help.
        'ambiguous.resolved': 'no', 'ambiguous.permanent': 'yes',
        'missing.resolved': 'no',
        'off.resolved': 'no',
        # The first report goes out, the repeat does not, a different problem does.
        'suspend.first': 'yes', 'suspend.again': 'no', 'suspend.changed': 'yes',
        'suspend.problem': 'ambiguous',
        'suspend.afterResume': 'none', 'suspend.reportsAgain': 'yes',
    }
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))
    for key, fragments in (
            ('ambiguous.problem', ('2 DICOM nodes are called that', 'AE104@127.0.0.1:104',
                                   'AE11112@127.0.0.1:11112', 'Nothing was sent')),
            ('missing.problem', ('there is no DICOM node of that name', 'renamed or removed',
                                 'nightly')),
            ('off.problem', ('exists but is not activated',)),
            ('empty.problem', ('names no destination',))):
        for fragment in fragments:
            if fragment not in results.get(key, ''):
                failures.append('%s does not say %r: %r' % (key, fragment, results.get(key)))

# --- the queue ----------------------------------------------------------------
if re.search(r'for \(NSDictionary\* aServer in serversArray\)\s*\n\s*if\( \[\[aServer objectForKey:@"Activated"\] boolValue\] '
             r'&& \[\[aServer objectForKey:@"Description"\] isEqualToString:serverName\]\)', routing):
    failures.append('the queue still takes the first node whose name matches')
for expected, missing in (
        ('HorosRoutingDestination destinationNamed:', 'the destination is not resolved'),
        ('HorosSuspendedRoutingRules suspendRule:', 'a rule that cannot resolve is not suspended'),
        ('HorosSuspendedRoutingRules resumeRule:', 'a rule fixed in the preferences stays suspended'),
        ('_routingDestinationProblem:', 'nothing is shown when the destination cannot be told')):
    if expected not in routing:
        failures.append(missing)

# The progress total has to count what will actually be sent, or the bar lies.
total = routing[routing.find('NSInteger total = 0;'):]
total = total[:400]
if 'destinationNamed:' not in total:
    failures.append('the progress total still counts by matching the name itself')

# And the problem reaches the user, not only the log.
alert = routing[routing.find('-(void)_routingDestinationProblem:'):]
alert = alert[:900]
if 'NSAlert' not in alert or 'setInformativeText' not in alert:
    failures.append('the destination problem is not shown')
if 'NSLog' not in alert:
    failures.append('the destination problem is not logged')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a rule resolves to exactly one activated node or sends nothing, and says which of '
      'renamed, removed, deactivated or duplicated happened')
