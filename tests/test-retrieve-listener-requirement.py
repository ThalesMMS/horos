#!/usr/bin/env python3
"""A WADO retrieval does not need the DICOM listener, and is no longer refused.

A C-MOVE asks the remote node to send the study to a separate application entity,
so something has to be listening: our own listener, or an explicit move
destination. A WADO retrieval is a C-FIND and then plain HTTP GETs; nothing
listens for those. -[QueryController performRetrieve:] refused every retrieval
when the listener was off, and returned with nothing but an NSLog, so a user who
runs no SCP was blocked from the one method that would have worked and was not
told why.

C-GET owns its storage context and needs no listener; C-MOVE still requires one
unless another move destination is supplied.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

# Neither gate in the query window may refuse or warn on its own any more.
controller = (root / 'Horos/Sources/QueryController.mm').read_bytes().decode('latin1')
gates, at = [], 0
while True:
    at = controller.find('[[AppController sharedAppController] isStoreSCPRunning] == NO', at)
    if at < 0:
        break
    gates.append(controller[at:at + 800])
    at += 1
if len(gates) != 2:
    failures.append('found %d listener gates in the query window, expected 2' % len(gates))
if not any('listenerRequiredForEveryRetrieveMode' in gate for gate in gates):
    failures.append('-performRetrieve: still refuses every retrieval when the listener is off')
if not any('listenerRequiredForServers' in gate for gate in gates):
    failures.append('the query window still warns whenever the listener is off')
# And the refusal has to reach the user, not only the log.
refusal = next((gate for gate in gates if 'listenerRequiredForEveryRetrieveMode' in gate), '')
if 'errorMessage:' not in refusal:
    failures.append('-performRetrieve: refuses without telling the user')

# Only the three C-MOVE refusals remain after request-owned C-GET storage.
node = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')
if node.count('Listener is not activated') != 3:
    failures.append('%d listener refusals in the retrieve path, expected 3 (C-MOVE only)'
                    % node.count('Listener is not activated'))

code = r'''
import Foundation

func check(_ mode: Int, _ destination: String?, _ expected: Bool, _ what: String) {
    let actual = RetrieveListenerRequirement.listenerRequired(forRetrieveMode: mode,
                                                              moveDestination: destination)
    precondition(actual == expected, "\(what): got \(actual), expected \(expected)")
}
// A C-MOVE with nowhere else to send needs the listener; with a destination it
// does not, because that destination is somebody else's listener.
check(0, nil, true, "C-MOVE with no destination")
check(0, "", true, "C-MOVE with an empty destination")
check(0, "OTHERAE", false, "C-MOVE to another application entity")
// WADO is plain HTTP.
check(2, nil, false, "WADO")
check(2, "OTHERAE", false, "WADO with a destination")
// C-GET receives on the association it opened.
check(1, nil, false, "C-GET")
check(1, "OTHERAE", false, "C-GET with a destination")
check(3, nil, false, "DICOMweb uses HTTP without a listener")
check(99, nil, true, "an unknown mode is treated as a C-MOVE")

func checkMode(_ server: [String: Any], _ expected: Int, _ what: String) {
    let actual = RetrieveListenerRequirement.retrieveMode(forServer: server)
    precondition(actual == expected, "\(what): got \(actual), expected \(expected)")
}
// The defaults DCMNetServiceDelegate applies when it normalises a stored node.
checkMode([:], 0, "a node with nothing stored")
checkMode(["retrieveMode": 2], 2, "a WADO node")
checkMode(["retrieveMode": "2"], 2, "a WADO node, string")
checkMode(["CGET": "1"], 1, "a legacy CGET node")
checkMode(["CGET": 1], 1, "a legacy CGET node, number")
checkMode(["CGET": "0"], 0, "a legacy node with CGET off")
checkMode(["retrieveMode": 0, "CGET": "1"], 0, "retrieveMode wins over the legacy flag")

func checkServers(_ servers: [[String: Any]]?, _ expected: Bool, _ what: String) {
    let actual = RetrieveListenerRequirement.listenerRequired(forServers: servers)
    precondition(actual == expected, "\(what): got \(actual), expected \(expected)")
}
checkServers(nil, false, "no configured nodes")
checkServers([], false, "an empty node list")
checkServers([["Description": "wado", "retrieveMode": 2]], false, "one WADO node")
checkServers([["Description": "plain"]], true, "a node with no retrieveMode")
checkServers([["Description": "off", "Activated": "0"]], false, "a deactivated C-MOVE node")
checkServers([["Description": "off", "Activated": 0]], false, "a deactivated node, number")
checkServers([["Description": "on", "Activated": 1, "retrieveMode": 0]], true, "an activated C-MOVE node")
// One affected node among several is enough, and none is not.
checkServers([["Description": "wado", "retrieveMode": 2],
              ["Description": "wado2", "retrieveMode": 2]], false, "only WADO nodes")
checkServers([["Description": "wado", "retrieveMode": 2],
              ["Description": "move", "retrieveMode": 0]], true, "a C-MOVE node among WADO ones")
checkServers([["Description": "wado", "retrieveMode": 2],
              ["Description": "move", "retrieveMode": 0, "Activated": "0"]], false,
             "the only C-MOVE node deactivated")

func checkBatch(_ modes: [Int], _ expected: Bool, _ what: String) {
    let actual = RetrieveListenerRequirement.listenerRequired(
        forEveryRetrieveMode: modes.map { NSNumber(value: $0) })
    precondition(actual == expected, "\(what): got \(actual), expected \(expected)")
}
checkBatch([], false, "an empty batch")
checkBatch([2], false, "a WADO batch")
checkBatch([0], true, "a C-MOVE batch")
checkBatch([1], false, "a C-GET batch")
checkBatch([0, 1], false, "C-MOVE and C-GET together")
// The point of the batch rule: one WADO node keeps the batch alive.
checkBatch([0, 2], false, "a WADO node among C-MOVE ones")
checkBatch([1, 2], false, "a WADO node among C-GET ones")
print("PASS: 8 retrieve modes, 7 stored-node shapes, 10 node lists and 7 batches; only a batch "
      + "in which every node needs the listener is refused")
'''

with tempfile.TemporaryDirectory(prefix='horos-retrieve-listener-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(code)
    compiled = subprocess.run(['xcrun', 'swiftc',
                               str(root / 'Horos/Sources/RetrieveListenerRequirement.swift'),
                               str(path / 'main.swift'), '-o', str(path / 'test')],
                              capture_output=True, text=True)
    if compiled.returncode != 0:
        print(compiled.stderr[-2000:])
        failures.append('the rule no longer compiles')
    else:
        run = subprocess.run([str(path / 'test')], capture_output=True, text=True)
        print((run.stdout or run.stderr).strip())
        if run.returncode != 0:
            failures.append('the rule does not hold')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a WADO retrieval is no longer refused for want of a listener, a refusal reaches the '
      'user, and the warning names only the nodes it applies to')
