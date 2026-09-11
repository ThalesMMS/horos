#!/usr/bin/env python3
"""A DICOM node that cannot be reached says why, and names the permission.

Every failure to reach a node reported the same sentence. It was
`0000:0001 Illegal parameter`, because -queryWithValues:dataset: read the real
condition from the association thread and then overwrote it one line later:

    cond = globalCondition;
    if( [dict objectForKey: @"assoc"]) assoc = …;
    else cond = EC_IllegalParameter;

With that corrected the condition is `0006:031b Failed to establish association`,
which is still the same for a closed port, an unknown host name, a firewall
dropping the packets, and macOS refusing the application access to the local
network. Since Sequoia that last one is a permission a user has to grant, and
nothing said so.

The reason is now established by making the connection ourselves and looking at
why it failed. That is Swift, and it is compiled and run here against real
sockets.
"""
from pathlib import Path
import plistlib
import re
import socket
import subprocess
import sys
import tempfile
import threading

root = Path(__file__).resolve().parents[1]
failures = []
diagnosis = root / 'Horos/Sources/NetworkDiagnosis.swift'
node = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')
scu = (root / 'Horos/Sources/DCMTKStoreSCU.mm').read_bytes().decode('latin1')

# A listening port proves TCP reachability, without implying DICOM rejection.
listener = socket.socket()
listener.bind(('127.0.0.1', 0))
listener.listen(4)
open_port = listener.getsockname()[1]
threading.Thread(target=lambda: [listener.accept() for _ in range(2)], daemon=True).start()

# And one that is not.
closed = socket.socket()
closed.bind(('127.0.0.1', 0))
closed_port = closed.getsockname()[1]
closed.close()

DRIVER = '''
import Foundation

func emit(_ key: String, _ value: String) { print(key + "\\t" + value) }

emit("private10", NetworkDiagnosis.isLocalNetworkAddress("10.1.2.3") ? "yes" : "no")
emit("private172", NetworkDiagnosis.isLocalNetworkAddress("172.20.0.1") ? "yes" : "no")
emit("private172low", NetworkDiagnosis.isLocalNetworkAddress("172.15.0.1") ? "yes" : "no")
emit("private192", NetworkDiagnosis.isLocalNetworkAddress("192.168.0.9") ? "yes" : "no")
emit("linkLocal", NetworkDiagnosis.isLocalNetworkAddress("169.254.1.1") ? "yes" : "no")
emit("bonjour", NetworkDiagnosis.isLocalNetworkAddress("pacs.local") ? "yes" : "no")
emit("public", NetworkDiagnosis.isLocalNetworkAddress("8.8.8.8") ? "yes" : "no")

emit("openProbe", String(NetworkDiagnosis.probe(host: "127.0.0.1", port: %(open)d, timeout: 2)))
emit("closedProbe", String(NetworkDiagnosis.probe(host: "127.0.0.1", port: %(closed)d, timeout: 2)))
emit("unresolvable", String(NetworkDiagnosis.probe(host: "no-such-host.invalid", port: 104, timeout: 2)))

emit("unrelatedFSM", NetworkDiagnosis.protocolExplanation("0006:0303 No action defined, state 6 event 17") ?? "unknown")
emit("tlsTransport", NetworkDiagnosis.protocolExplanation("DUL secure transport layer: wrong version number") ?? "unknown")
emit("tls", NetworkDiagnosis.explainFailure(toHost: "127.0.0.1", port: %(closed)d, condition: "0006:031e DUL secure transport layer: certificate verify failed"))
emit("associationTimeout", NetworkDiagnosis.explainFailure(toHost: "127.0.0.1", port: %(closed)d, condition: "0006:0303 DUL Finite State Machine Error: No action defined, state 5 event 17"))
emit("rejected", NetworkDiagnosis.explainFailure(toHost: "127.0.0.1", port: %(closed)d, condition: "Association Rejected : 0006:0301"))
emit("open", NetworkDiagnosis.explainFailure(toHost: "127.0.0.1", port: %(open)d, condition: "0006:031b"))
emit("closed", NetworkDiagnosis.explainFailure(toHost: "127.0.0.1", port: %(closed)d, condition: nil))
emit("name", NetworkDiagnosis.explainFailure(toHost: "no-such-host.invalid", port: 104, condition: nil))
emit("unreachableLocal", NetworkDiagnosis.explanation(forErrno: EHOSTUNREACH, host: "192.168.1.9",
                                                      port: 104, isLocalNetwork: true))
emit("unreachablePublic", NetworkDiagnosis.explanation(forErrno: EHOSTUNREACH, host: "8.8.8.8",
                                                       port: 104, isLocalNetwork: false))
emit("timeoutLocal", NetworkDiagnosis.explanation(forErrno: -1, host: "192.168.1.9", port: 104,
                                                  isLocalNetwork: true))
''' % {'open': open_port, 'closed': closed_port}

results = {}
swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'], capture_output=True, text=True)
if swiftc.returncode != 0:
    failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
else:
    with tempfile.TemporaryDirectory(prefix='horos-network-') as directory:
        # Top-level statements are only allowed in a file called main.swift.
        (Path(directory) / 'main.swift').write_text(DRIVER)
        binary = Path(directory) / 'network'
        built = subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                                str(diagnosis), str(Path(directory) / 'main.swift')],
                               capture_output=True, text=True)
        if built.returncode != 0:
            failures.append('the diagnosis does not compile:\n%s' % built.stderr[-1500:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append('the diagnosis driver failed: %s' % run.stderr[-800:])
            for line in run.stdout.splitlines():
                key, _, value = line.partition('\t')
                results[key] = value
listener.close()

if results:
    expected = {
        'unrelatedFSM': 'unknown', 'private10': 'yes', 'private172': 'yes', 'private172low': 'no', 'private192': 'yes',
        'linkLocal': 'yes', 'bonjour': 'yes', 'public': 'no',
        # A real socket: one listening, one not, one name that does not resolve.
        'openProbe': '0', 'closedProbe': '61', 'unresolvable': '-2',
    }
    for key, value in expected.items():
        if results.get(key) != value:
            failures.append('%s is %r, expected %r' % (key, results.get(key), value))
    checks = (
        ('open', ('accepted a diagnostic TCP connection', 'TCP reachability only', '0006:031b')),
        ('tlsTransport', ('TLS connection failed', 'cipher suites')),
        ('tls', ('TLS certificate verification failed', 'trust policy', 'certificate verify failed')),
        ('associationTimeout', ('before the timeout', 'no association rejection was confirmed', 'state 5 event 17')),
        ('rejected', ('peer rejected', 'calling AE titles', '0006:0301')),
        ('closed', ('Nothing is listening', 'not a network permission')),
        ('name', ('could not be resolved',)),
        ('unreachableLocal', ('no route', 'Local Network', 'Sequoia')),
        ('timeoutLocal', ('No answer', 'Local Network')),
    )
    for key, fragments in checks:
        for fragment in fragments:
            if fragment not in results.get(key, ''):
                failures.append('%s does not say %r: %r' % (key, fragment, results.get(key)))
    # The advice is only given where it applies.
    if 'Local Network' in results.get('unreachablePublic', ''):
        failures.append('the local network advice is given for a public address')
    if 'Local Network' in results.get('closed', ''):
        failures.append('a refused connection is blamed on the local network permission')

# --- the condition is no longer thrown away ----------------------------------
if re.search(r'else\s*\n\s*cond = EC_IllegalParameter;', node):
    failures.append('the association condition is overwritten again')
if 'else if( cond == EC_Normal)' not in node:
    failures.append('the fallback no longer keeps the reason the thread reported')

# --- and both association failures explain themselves ------------------------
for source, name in ((node, 'the query'), (scu, 'the send')):
    if source.count('HorosNetworkDiagnosis explainFailureToHost:') != 2:
        failures.append('%s does not explain both a rejected and a failed association' % name)

# --- the permission is declared ----------------------------------------------
info = plistlib.loads((root / 'Horos/Info.plist').read_bytes())
description = info.get('NSLocalNetworkUsageDescription')
if not description:
    failures.append('Info.plist does not declare why the application needs the local network')
elif 'DICOM' not in description:
    failures.append('the local network description does not say what it is for: %r' % description)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a node that cannot be reached is told apart from one that refuses the association, '
      'and a local address that will not route names the Local Network permission')
