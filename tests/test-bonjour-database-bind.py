#!/usr/bin/env python3
"""Database sharing names the port and errno when bind on 8780 fails.

#389 already reports the DICOM listener, XML-RPC and the web portal through
ListenBindFailure. The Bonjour database share is a fourth N2ConnectionListener
on 8780; a failed bind used to log only 'Warning: unable to share Horos
database'. This issue is #392, not a reopen of #389.
"""
from pathlib import Path
import errno
import socket
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

helper = root / 'Horos/Sources/ListenBindFailure.swift'
publisher = (root / 'Horos/Sources/BonjourPublisher.m').read_bytes().decode('latin1')
app = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')

SERVICE = 'database sharing'
PORT = 8780


def method(source, signature):
    start = source.find(signature)
    if start < 0:
        return ''
    opening = source.find('{', start)
    depth = 0
    for end in range(opening, len(source)):
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
            if depth == 0:
                return source[start:end + 1]
    return ''


def hold(port):
    sockets = []
    occupied = False
    for family, address in ((socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::')):
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        if family == socket.AF_INET6:
            try:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            except OSError:
                pass
        try:
            sock.bind((address, port))
        except OSError as error:
            sock.close()
            if error.errno == errno.EADDRINUSE:
                occupied = True
                continue
            raise
        sock.listen(1)
        sockets.append(sock)
        occupied = True
    return sockets, occupied


def second_bind_errno(port):
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(('0.0.0.0', port))
        probe.close()
        return 0
    except OSError as error:
        probe.close()
        return error.errno


toggle = method(publisher, '- (void)toggleSharing:(BOOL)activate')
if not toggle:
    failures.append('BonjourPublisher is missing toggleSharing:')

# Failure path: same AppController funnel as the other three listeners.
if 'reportListenBindFailure' not in toggle:
    failures.append('toggleSharing: does not report a bind failure through AppController')
if 'lastBindErrno' not in toggle:
    failures.append('toggleSharing: does not pass N2ConnectionListener lastBindErrno')
if '8780' not in toggle or 'port:8780' not in toggle.replace(' ', ''):
    failures.append('toggleSharing: does not name port 8780 on bind failure')
if 'unable to share Horos database' in toggle:
    failures.append('toggleSharing: still logs the vague Warning without service/port/errno')
if SERVICE not in toggle and 'databaseSharingService' not in toggle:
    failures.append('toggleSharing: does not name the database sharing service')

# Success stays a single shared-on-port line; no false bind alert.
if 'Horos database shared on port' not in toggle:
    failures.append('successful sharing dropped its port log')
success = ''
if 'if (_listener)' in toggle:
    success = toggle[toggle.find('if (_listener)'):toggle.find('else')]
if 'reportListenBindFailure' in success:
    failures.append('the sharing success path reports a bind failure')

# Once, without blocking the thread that asked to share.
if 'waitUntilDone:YES' in toggle or 'NSRunAlertPanel' in toggle or 'runModal' in toggle:
    failures.append('toggleSharing: still blocks on a modal bind-failure alert')
if 'reportListenBindFailureForService' not in app or 'consumeUserNotice' not in app:
    failures.append('AppController no longer gates the user notice to once per service/port')
if 'presentUserNotice' not in app:
    failures.append('AppController no longer presents the notice off the listen thread')

# #259 stays on its own front.
if 'AsyncSocket lastBindErrno' in publisher:
    failures.append('BonjourPublisher started reading AsyncSocket; it binds through N2ConnectionListener')

helper_text = helper.read_text() if helper.is_file() else ''
if 'databaseSharingService' not in helper_text:
    failures.append('ListenBindFailure has no databaseSharingService name')
if SERVICE not in helper_text:
    failures.append('ListenBindFailure does not define the database sharing service string')
if 'port errno:' in helper_text or 'port:errno:)' in helper_text:
    failures.append('the ObjC selector still uses errno:, which the C macro expands in Horos-Swift.h')

if not helper.is_file():
    failures.append('Horos/Sources/ListenBindFailure.swift is missing')
else:
    held = []
    try:
        sockets, occupied = hold(PORT)
        held.extend(sockets)
        code = second_bind_errno(PORT) if sockets else (errno.EADDRINUSE if occupied else 0)
        if code != errno.EADDRINUSE:
            failures.append('holding port 8780 did not produce EADDRINUSE on a second bind '
                            '(got %s); the fixture is not occupying the port'
                            % (code or 'success'))
    except OSError as error:
        failures.append('could not hold port 8780: %s' % error)

    driver = r'''
import Foundation

ListenBindFailure.resetUserNoticesForTests()

let used = Int32(48) // EADDRINUSE on Darwin
let service = ListenBindFailure.databaseSharingService
precondition(service == "database sharing", "unexpected service name: \(service)")

let translation = ListenBindFailure.translatedErrno(used)
precondition(translation.lowercased().contains("address already in use")
             || translation.lowercased().contains("in use"),
             "errno 48 is not translated: \(translation)")

let line = ListenBindFailure.logLine(service: service, port: 8780, errno: used)
precondition(line.contains(service), "log omitted service: \(line)")
precondition(line.contains("8780"), "log omitted port: \(line)")
precondition(line.contains("48") || line.contains(translation), "log omitted errno: \(line)")
precondition(line.lowercased().contains("in use") || line.contains(translation),
             "log omitted the translation: \(line)")

let message = ListenBindFailure.userMessage(service: service, port: 8780, errno: used)
precondition(message.contains(service), "user message omitted service: \(message)")
precondition(message.contains("8780"), "user message omitted port: \(message)")

ListenBindFailure.resetUserNoticesForTests()
precondition(ListenBindFailure.consumeUserNotice(service: service, port: 8780))
precondition(!ListenBindFailure.consumeUserNotice(service: service, port: 8780),
             "the same service/port alerted twice")
precondition(ListenBindFailure.consumeUserNotice(service: service, port: 8781),
             "a different port was treated as a repeat")

print("PASS: database sharing, port 8780 and errno; notice once")
'''
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'],
                            capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-bonjour-bind-') as directory:
            main = Path(directory) / 'main.swift'
            main.write_text(driver)
            binary = Path(directory) / 'bind'
            built = subprocess.run(
                ['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
                 str(helper), str(main)],
                capture_output=True, text=True)
            if built.returncode != 0:
                failures.append('the listen-bind helper does not compile:\n%s'
                                % built.stderr[-1500:])
            else:
                run = subprocess.run([str(binary)], capture_output=True, text=True)
                if run.returncode != 0:
                    failures.append('the listen-bind helper failed: %s %s'
                                    % (run.stdout[-400:], run.stderr[-800:]))
                elif 'PASS:' not in run.stdout:
                    failures.append('the listen-bind helper printed nothing useful: %r'
                                    % run.stdout)

    for sock in held:
        sock.close()

# The helper is compiled above; a live Horos against an occupied 8780 is a
# separate validation. This test does not launch the app.

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: database sharing bind failure names the service, port 8780 and errno; '
      'the user is told once; holding 8780 produces EADDRINUSE')
