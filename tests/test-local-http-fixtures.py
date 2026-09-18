#!/usr/bin/env python3
"""A local HTTP fixture listens without asking the DNS (#647).

`http.server.HTTPServer.server_bind` calls `socket.getfqdn(host)`. On a Mac whose
reverse resolution of 127.0.0.1 has nowhere to go, that takes 35 s, and every
fixture paid it before it could listen: `tests/test-hierarchical-image-query.py`
gave up at 30 s with an empty log, and the others were 35 s slower each.

Checked here:

* no fixture of `tools/` and no test builds `http.server.HTTPServer` or
  `ThreadingHTTPServer` itself; they use `local_http`, which binds through
  `socketserver.TCPServer`;
* with `socket.getfqdn` replaced by a five-second wait, a `ThreadingLocalHTTPServer`
  is listening and answering in under two seconds, and `http.server`'s own server
  takes the whole wait;
* the name and port it reports are the address it was given.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

# The stock classes, not the local ones: ThreadingLocalHTTPServer ends in the same word.
DIRECT = re.compile(r'(?<![A-Za-z_])(?:http\.server\.)?(?:Threading)?HTTPServer\s*\(')
for folder in ('tools', 'tests'):
    for path in sorted((root / folder).glob('*.py')):
        if path.name == 'local_http.py' or path.name == Path(__file__).name:
            continue
        text = path.read_text(errors='replace')
        for number, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            if DIRECT.search(line):
                failures.append(f'{folder}/{path.name}:{number} builds its own HTTP server: {line.strip()} '
                                f'(use local_http, which does not resolve the host)')
        if 'getfqdn' in text:
            failures.append(f'{folder}/{path.name} calls getfqdn')

driver = r'''
import socket, sys, threading, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from local_http import ThreadingLocalHTTPServer
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WAIT = 5.0
def slow_getfqdn(name=''):
    time.sleep(WAIT)
    return 'slow.invalid'
socket.getfqdn = slow_getfqdn

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'ok')
    def log_message(self, *arguments):
        pass

started = time.monotonic()
server = ThreadingLocalHTTPServer(('127.0.0.1', 0), Handler)
bound = time.monotonic() - started
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]
answer = urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=5).read()
ready = time.monotonic() - started
name = server.server_name
server.shutdown()

started = time.monotonic()
stock = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
stock_bound = time.monotonic() - started
stock.server_close()
print(repr({'bound': bound, 'ready': ready, 'answer': answer.decode(), 'name': name,
            'port': port, 'stock_bound': stock_bound, 'wait': WAIT}))
'''

if not failures:
    with tempfile.TemporaryDirectory(prefix='horos-local-http-') as temporary:
        work = Path(temporary)
        (work / 'local_http.py').write_text((root / 'tools/local_http.py').read_text())
        (work / 'driver.py').write_text(driver)
        run = subprocess.run([sys.executable, str(work / 'driver.py')], capture_output=True, text=True, timeout=120)
        if run.returncode != 0:
            failures.append('the fixture server did not run: ' + (run.stdout + run.stderr)[-1500:])
        else:
            result = eval(run.stdout.strip())
            if result['ready'] > 2:
                failures.append(f"a fixture took {result['ready']:.2f} s to answer with a slow resolver")
            if result['answer'] != 'ok':
                failures.append(f"the fixture answered {result['answer']!r}")
            if result['name'] != '127.0.0.1' or result['port'] <= 0:
                failures.append(f"the fixture reports {result['name']}:{result['port']}, not the address it was given")
            if result['stock_bound'] < result['wait'] - 1:
                failures.append(f"http.server's own server bound in {result['stock_bound']:.2f} s: the slow resolver "
                                f"was not in its way, so this proves nothing")
            print(f"with a {result['wait']:.0f} s resolver: local fixture ready in {result['ready']:.2f} s, "
                  f"http.server's own bound in {result['stock_bound']:.2f} s")

if failures:
    print('\n'.join('FAIL: ' + failure for failure in failures))
    raise SystemExit(1)
print('local HTTP fixtures: no getfqdn, listening at once, and the address they were given')
