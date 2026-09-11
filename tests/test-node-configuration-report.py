#!/usr/bin/env python3
"""A failed query or retrieval says what the node is configured as.

When one workstation retrieves and another does not, the difference is in the
configuration, and the failure said only the called AE title, the host and the
port:

    NOBODY  /  127.0.0.1:11199

    DICOM Network Failure (query) …

Everything that could differ - the calling AE title, the retrieve method, the
transfer syntax, TLS, the WADO settings - had to be read off two screens side by
side. The block is now written in a fixed order with every field present, so two
of them differ only where the configurations do.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
configuration = root / 'Horos/Sources/DicomNodeConfiguration.swift'
node = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')

DRIVER = r'''
import Foundation

func emit(_ key: String, _ value: String) {
    print(key + "\t" + value.replacingOccurrences(of: "\n", with: " | "))
}

let move: [String: Any] = ["AETitle": "PACS", "Address": "10.0.0.4", "Port": "104",
                           "retrieveMode": 0, "TransferSyntax": 0, "Activated": "1"]
let wado: [String: Any] = ["AETitle": "PACS", "Address": "10.0.0.4", "Port": "104",
                           "retrieveMode": 2, "TransferSyntax": 1, "Activated": "1",
                           "WADOUrl": "wado", "WADOPort": 8080, "WADOhttps": 1,
                           "WADOTransferSyntax": 0]
let bare: [String: Any] = ["AETitle": "PACS"]

emit("move", DicomNodeConfiguration.description(forServer: move, callingAETitle: "HOROS"))
emit("wado", DicomNodeConfiguration.description(forServer: wado, callingAETitle: "HOROS"))
emit("bare", DicomNodeConfiguration.description(forServer: bare, callingAETitle: nil))

// The WADO settings appear only where they mean something.
emit("moveHasWado", DicomNodeConfiguration.description(forServer: move, callingAETitle: "H")
     .contains("WADO") ? "yes" : "no")

// Two profiles, differing in the two things that matter.
let other: [String: Any] = ["AETitle": "PACS", "Address": "10.0.0.4", "Port": "104",
                            "retrieveMode": 1, "TransferSyntax": 0, "Activated": "1"]
emit("differences", DicomNodeConfiguration.differences(betweenServer: move, andServer: other,
                                                       callingAETitle: "HOROS",
                                                       otherCallingAETitle: "OTHER")
     .joined(separator: " ; "))
emit("same", DicomNodeConfiguration.differences(betweenServer: move, andServer: move,
                                                callingAETitle: "HOROS",
                                                otherCallingAETitle: "HOROS").count.description)
'''

results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-node-config-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'configuration'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(configuration), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the configuration does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the configuration driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value

if results:
    move = results.get('move', '')
    for fragment in ('calling AE title     HOROS', 'called AE title      PACS',
                     'address              10.0.0.4', 'port                 104',
                     'retrieve             C-MOVE', 'transfer syntax      explicit little endian',
                     'TLS                  off', 'activated            yes'):
        if fragment not in move:
            failures.append('the block does not carry %r: %r' % (fragment, move))
    wado = results.get('wado', '')
    for fragment in ('retrieve             WADO', 'transfer syntax      JPEG 2000 lossless',
                     'WADO url             wado', 'WADO port            8080',
                     'WADO https           on'):
        if fragment not in wado:
            failures.append('the WADO block does not carry %r: %r' % (fragment, wado))
    if results.get('moveHasWado') != 'no':
        failures.append('the WADO settings are shown for a node that does not use WADO')
    bare = results.get('bare', '')
    # Every field is present even when unset, or two blocks cannot be compared.
    for fragment in ('calling AE title     (none)', 'address              (none)',
                     'port                 (none)', 'retrieve             C-MOVE',
                     'activated            yes'):
        if fragment not in bare:
            failures.append('an unset field is missing from the block instead of empty: %r' % bare)
            break
    if results.get('differences') != 'calling AE title: HOROS vs OTHER ; retrieve: C-MOVE vs C-GET':
        failures.append('the difference between two profiles is %r' % results.get('differences'))
    if results.get('same') != '0':
        failures.append('two identical profiles are reported as differing')

# --- every failure that names a node carries it ------------------------------
count = node.count('HorosDicomNodeConfiguration descriptionForServer:')
if count < 5:
    failures.append('only %d of the query, move and get failures document the configuration'
                    % count)
for anchor, name in (('Query Failed (1)', 'the query'), ('Move Failed', 'the move'),
                     ('Get Failed', 'the get')):
    at = node.find(anchor)
    if at < 0:
        failures.append('%s failure is gone' % name)
        continue
    # The block is built in the same statement that builds the message.
    window = node[max(at - 700, 0):at + 700]
    if 'HorosDicomNodeConfiguration' not in window:
        failures.append('%s failure does not document the configuration' % name)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a failed query, move or get carries the node it was talking to, in a fixed order with '
      'every field present, so two profiles can be compared')
