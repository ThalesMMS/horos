#!/usr/bin/env python3
"""#597: exercise the real CLI against a loopback XML-RPC contract server.

An optional git ref runs the delayed-opening regression against that old helper.
No application, DICOM data, database or external network service is involved.
"""
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import xmlrpc.client
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from local_http import ThreadingLocalHTTPServer  # a fixture binds without the DNS (#647)

root = Path(__file__).resolve().parents[1]
UID_A, UID_B = '1.2.3.4', '1.2.3.5'


def response(payload):
    # Horos also emits untyped <value>text</value>, valid XML-RPC strings.
    tree = ET.fromstring(xmlrpc.client.dumps((payload,), methodresponse=True))
    for value in tree.iter('value'):
        if len(value) == 1 and value[0].tag == 'string':
            value.text = value[0].text
            value.remove(value[0])
    return ET.tostring(tree)


def series(*uids):
    return {'error': '0', 'elements': [
        {'name': 'QA & Sync', 'seriesDICOMUID': uid, 'numberOfImages': 16} for uid in uids]}


@contextmanager
def server(dispatch):
    requests = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            values, method = xmlrpc.client.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                requests.append((method, values[0]))
            status, payload = dispatch(method, values[0])
            data = payload if isinstance(payload, bytes) else response(payload)
            try:
                self.send_response(status)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the bounded-timeout case intentionally closes its socket

    http = ThreadingLocalHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: http.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield http.server_port, requests
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def run(script, dispatch, args, expected=0, diagnostic=None):
    with server(dispatch) as (port, requests):
        result = subprocess.run([sys.executable, str(script), '--port', str(port), *args],
                                capture_output=True, text=True, timeout=5)
    assert result.returncode == expected, (args, result.returncode, result.stdout, result.stderr)
    assert 'Traceback' not in result.stderr, result.stderr
    if diagnostic:
        assert diagnostic in result.stderr, result.stderr
    return result, requests


def delayed(script, concurrent=False):
    polls = 0

    def dispatch(method, params):
        nonlocal polls
        if method == 'GetDisplayed2DViewerSeries':
            polls += 1
            return 200, series(*(uids if polls >= 3 else []))
        return 200, {'error': '0'}

    uids = [UID_A, UID_B] if concurrent else [UID_A]
    result, _ = run(script, dispatch, (['--concurrent'] if concurrent else []) + uids)
    assert polls == 3, polls
    assert 'observed' in result.stdout


with tempfile.TemporaryDirectory(prefix='horos-open-helper-') as temporary:
    script = root / 'tools/open-series-xmlrpc.py'
    if len(sys.argv) > 1:
        source = subprocess.check_output(['git', 'show', sys.argv[1] + ':tools/open-series-xmlrpc.py'])
        script = Path(temporary) / script.name
        script.write_bytes(source)
        delayed(script)  # old helper must fail by misdiagnosing the pending ACK
        raise SystemExit(0)

    delayed(script)
    delayed(script, concurrent=True)
    for displayed in ([], [UID_B]):
        result, _ = run(script, lambda m, p: (200, series(*displayed) if m.startswith('GetDisplayed') else {'error': '0'}),
                        ['--wait-timeout', '0.1', UID_A], 1, 'missing SeriesInstanceUID(s): ' + UID_A)
        assert 'the application is closing' not in result.stderr

    for concurrent in (False, True):
        for refusal in ('protocol', 'transport'):
            def dispatch(method, params):
                if method == 'DisplaySeries' and params['SeriesInstanceUID'] == UID_B:
                    return (503, b'') if refusal == 'transport' else (200, {'error': '409'})
                return 200, series(UID_A, UID_B) if method.startswith('GetDisplayed') else {'error': '0'}
            args = (['--concurrent'] if concurrent else []) + [UID_A, UID_B]
            result, _ = run(script, dispatch, args, 1, UID_B)
            assert ('503' if refusal == 'transport' else '409') in result.stderr

    _, requests = run(script, lambda m, p: (200, {'error': '403'}),
                      ['--close-first', UID_A], 1, 'CloseAllWindows returned error 403')
    assert [m for m, _ in requests] == ['CloseAllWindows']
    run(script, lambda m, p: (200, {'error': '500'} if m.startswith('GetDisplayed') else {'error': '0'}),
        [UID_A], 1, 'GetDisplayed2DViewerSeries returned error 500')
    run(script, lambda m, p: (200, b'<broken'), [UID_A], 1, 'invalid XML-RPC response')
    run(script, lambda m, p: (200, {}), [UID_A], 1, 'error (missing)')
    run(script, lambda m, p: (200, {'error': '0'}), [UID_A], 1, 'no valid elements array')

    result, requests = run(script, lambda m, p: (200, series(UID_A) if m.startswith('GetDisplayed') else {'error': '0'}),
                           ['--repeat', '2', UID_A, UID_A])
    assert Counter(m for m, _ in requests)['DisplaySeries'] == 4
    assert result.stdout.count('all 1 requested UID(s) observed') == 2

    result, requests = run(script, lambda m, p: (200, series(UID_A, UID_B)), ['--list', '--patient', 'QA-597'])
    assert [m for m, _ in requests] == ['DBWindowFind']
    assert 'QA & Sync' in result.stdout and UID_A in result.stdout and UID_B in result.stdout
    run(script, lambda m, p: (200, {'error': '400'}), ['--list', '--patient', 'QA-597'], 1, 'error 400')

    for timeout in ('0', '-1', 'nan', 'inf'):
        _, requests = run(script, lambda m, p: (200, {'error': '0'}),
                          ['--wait-timeout', timeout, UID_A], 2, 'finite and greater than zero')
        assert not requests

    def slow_query(method, params):
        if method.startswith('GetDisplayed'):
            time.sleep(0.4)
            return 200, series(UID_A)
        return 200, {'error': '0'}
    started = time.monotonic()
    run(script, slow_query, ['--wait-timeout', '0.1', UID_A], 1, 'missing SeriesInstanceUID(s)')
    assert time.monotonic() - started < 1

print('PASS: delayed ACKs, UID identity, bounded wait, sequential/concurrent failures, close-first, malformed responses, list and repeat')
