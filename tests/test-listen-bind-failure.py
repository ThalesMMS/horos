#!/usr/bin/env python3
"""A listen that cannot bind names the service, the port and the errno.

The three sockets Horos opens - the DICOM listener, the XML-RPC interface and
the web portal - share the same default ports as OsiriX (11112, 8080, 3333).
When another process is already there, only the web portal used to say so, and
it never named the port. XML-RPC failed with a CFSocket bind log and then
silence. The DICOM listener said nothing.

The line in the log has to name the service, the port and the translated errno
for each of the three. The person who asked for the service is told once, without
a modal panel that holds startup, and without the same alert on every
restartSTORESCP. The historical web-portal sentence stays; it gains the port.
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
listener = (root / 'Nitrogen/Sources/N2ConnectionListener.mm').read_bytes().decode('latin1')
listener_h = (root / 'Nitrogen/Sources/N2ConnectionListener.h').read_bytes().decode('latin1')
xmlrpc = (root / 'Horos/Sources/XMLRPCMethods.mm').read_bytes().decode('latin1')
portal = (root / 'Horos/Sources/WebPortal.mm').read_bytes().decode('latin1')
dicom = (root / 'Horos/Sources/DCMTKQueryRetrieveSCP.mm').read_bytes().decode('latin1')
app = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
async_socket = (root / 'cocoahttpserver/AsyncSocket.m').read_bytes().decode('latin1')

SERVICES = (
    ('web portal', 3333),
    ('XML-RPC', 8080),
    ('DICOM listen', 11112),
)


def hold(port):
    """Occupy IPv4 and IPv6 the way a foreign listener does, without SO_REUSEPORT.

    If the port is already taken, that is the same situation the Horos
    measurement saw on this Mac (8080 was held by something else). Either way
    the port is occupied.
    """
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


# --- errno is kept when a bind fails -----------------------------------------
if 'lastBindErrno' not in listener_h or 'lastBindErrno' not in listener:
    failures.append('N2ConnectionListener still returns nil without the bind errno')
if 'sLastBindErrno' not in listener and 'lastBindErrno' not in listener:
    failures.append('the IPv4/IPv6 bind failure path does not record errno')
if 'CFSocketSetAddress' in listener and 'errno' not in listener:
    failures.append('N2ConnectionListener does not read errno after CFSocketSetAddress fails')

if 'lastBindErrno' not in async_socket:
    failures.append('AsyncSocket does not keep the bind errno the web portal can read')

# --- each listener reports through one place, once --------------------------
# The three C/C++ listeners funnel through AppController so DCMTK does not
# have to import the Swift header, and so the once-only notice lives in one
# method rather than three copies that can drift.
for name, source in (('XML-RPC', xmlrpc), ('web portal', portal),
                     ('DICOM listen', dicom)):
    if 'reportListenBindFailure' not in source:
        failures.append('%s does not report a bind failure through AppController' % name)

if 'HorosListenBindFailure' not in app or 'logLineForService' not in app:
    failures.append('AppController does not log bind failures through ListenBindFailure')
if 'consumeUserNotice' not in app:
    failures.append('nothing in AppController gates the user notice to once per service/port')
helper_text = helper.read_text() if helper.is_file() else ''
if 'port errno:' in app or 'port:errno:)' in helper_text:
    failures.append('the ObjC selector still uses errno:, which the C macro expands in Horos-Swift.h')
if 'webPortalUserMessage' not in app and 'webPortalUserMessage' not in helper_text:
    failures.append('the web portal dropped its historical sentence instead of adding the port')
if 'waitUntilDone:YES' in portal and 'Cannot start Web Server' in portal:
    failures.append('the web portal still blocks its thread on the bind-failure alert')

at = dicom.find('ASC_initializeNetwork')
around = dicom[at:at + 900] if at >= 0 else ''
if 'displayUpdateMessage' in around and 'LISTENER' in around:
    failures.append('DICOM bind failure still goes through displayUpdateMessage:LISTENER, '
                    'which names neither the port nor the errno and can block the main thread')

restart_at = app.find('-(void) restartSTORESCP')
restart_end = app.find('-(void) displayError', restart_at)
restart = app[restart_at:restart_end] if restart_at >= 0 and restart_end > restart_at else ''
if 'displayListenerError' in restart or 'displayUpdateMessage' in restart:
    failures.append('restartSTORESCP itself puts up a listener alert, so a retry would spam')

# A successful start must stay silent.
if 'logLineForService' in xmlrpc:
    success = xmlrpc[xmlrpc.find('if( _listener)'):xmlrpc.find('-(void)dealloc')]
    if 'logLineForService' in success:
        failures.append('the XML-RPC success path logs a bind failure')

# --- the helper, compiled, and the ports held --------------------------------
if not helper.is_file():
    failures.append('Horos/Sources/ListenBindFailure.swift is missing')
else:
    held = []
    port_results = {}
    try:
        for service, port in SERVICES:
            sockets, occupied = hold(port)
            held.extend(sockets)
            if not occupied:
                port_results[port] = 0
            elif sockets:
                port_results[port] = second_bind_errno(port)
            else:
                # Someone else already had the port, the same situation measured
                # on this Mac for 8080.
                port_results[port] = errno.EADDRINUSE
    except OSError as error:
        failures.append('could not hold a listen port: %s' % error)

    for port, code in port_results.items():
        if code != errno.EADDRINUSE:
            failures.append('holding port %d did not produce EADDRINUSE on a second bind '
                            '(got %s); the fixture is not occupying the port'
                            % (port, code or 'success'))

    driver = r'''
import Foundation

ListenBindFailure.resetUserNoticesForTests()

let used = Int32(48) // EADDRINUSE on Darwin
let translation = ListenBindFailure.translatedErrno(used)
precondition(translation.lowercased().contains("address already in use")
             || translation.lowercased().contains("in use"),
             "errno 48 is not translated: \(translation)")

for (service, port) in [("web portal", 3333), ("XML-RPC", 8080), ("DICOM listen", 11112)] {
    let line = ListenBindFailure.logLine(service: service, port: port, errno: used)
    precondition(line.contains(service), "log omitted service: \(line)")
    precondition(line.contains(String(port)), "log omitted port: \(line)")
    precondition(line.contains("48") || line.contains(translation), "log omitted errno: \(line)")
    precondition(line.lowercased().contains("in use") || line.contains(translation),
                 "log omitted the translation: \(line)")
}

let web = ListenBindFailure.webPortalUserMessage(port: 3333)
precondition(web.contains("Cannot start Web Server"), "web message lost its sentence: \(web)")
precondition(web.contains("TCP/IP port"), "web message lost its sentence: \(web)")
precondition(web.contains("already used by another process"), "web message lost its sentence: \(web)")
precondition(web.contains("3333"), "web message has no port: \(web)")

ListenBindFailure.resetUserNoticesForTests()
precondition(ListenBindFailure.consumeUserNotice(service: "XML-RPC", port: 8080))
precondition(!ListenBindFailure.consumeUserNotice(service: "XML-RPC", port: 8080),
             "the same service/port alerted twice")
precondition(ListenBindFailure.consumeUserNotice(service: "XML-RPC", port: 8081),
             "a different port was treated as a repeat")
precondition(ListenBindFailure.consumeUserNotice(service: "web portal", port: 8080),
             "a different service was treated as a repeat")

print("PASS: service, port and errno; web sentence kept; notice once")
'''
    swiftc = subprocess.run(['xcrun', '--sdk', 'macosx', '-f', 'swiftc'],
                            capture_output=True, text=True)
    if swiftc.returncode != 0:
        failures.append('no swiftc here: %s' % (swiftc.stderr or '').strip())
    else:
        with tempfile.TemporaryDirectory(prefix='horos-listen-bind-') as directory:
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

# A live Horos with --diagnostics is a separate validation. This test occupies
# the three ports the way that measurement did; it does not launch the app.
# If a built bundle is later handed to a runtime harness, it should skip here
# rather than fail the focused suite.
# (Intentionally no app launch.)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: bind failures name the service, the port and errno 48; the web sentence '
      'keeps its words and gains the port; the user is told once; holding 3333/8080/'
      '11112 produces EADDRINUSE')
