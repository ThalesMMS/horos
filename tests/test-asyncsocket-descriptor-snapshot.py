#!/usr/bin/env python3
"""#513: socket accounting must exclude other processes and mapped files."""
import ast
from pathlib import Path
import select
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
source = root / 'tests/test-asyncsocket-reset-close.py'
tree = ast.parse(source.read_text())
function = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == 'descriptor_snapshot')
namespace = {'subprocess': subprocess}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
snapshot = namespace['descriptor_snapshot']

# The foreign process keeps an actual reset TCP descriptor and a regular FD.
# This makes both the -p/-i OR mistake and counting txt/cwd deterministic.
fixture = r'''
import socket, struct, sys
print('ready', flush=True)
sys.stdin.readline()
listener = socket.socket()
listener.bind(('127.0.0.1', 0))
listener.listen()
client = socket.create_connection(listener.getsockname())
server, _ = listener.accept()
listener.close()
client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
client.close()
extra = open('/dev/null')
print('holding', flush=True)
sys.stdin.readline()
server.close()
extra.close()
print('released', flush=True)
sys.stdin.readline()
'''


def await_line(process, expected):
    assert select.select([process.stdout], [], [], 5)[0], 'fixture stalled'
    assert process.stdout.readline().strip() == expected


innocent = subprocess.Popen(['sleep', '30'])
foreign = subprocess.Popen([sys.executable, '-c', fixture], stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
try:
    await_line(foreign, 'ready')
    baseline = snapshot(foreign.pid)
    innocent_baseline = snapshot(innocent.pid)
    assert baseline == (0, 3), baseline
    foreign.stdin.write('open\n')
    foreign.stdin.flush()
    await_line(foreign, 'holding')
    assert snapshot(foreign.pid) == (1, 5), snapshot(foreign.pid)
    assert snapshot(innocent.pid) == innocent_baseline, 'another PID affected the counts'
    foreign.stdin.write('close\n')
    foreign.stdin.flush()
    await_line(foreign, 'released')
    assert snapshot(foreign.pid) == baseline, 'real descriptors did not return to baseline'
finally:
    for process in (foreign, innocent):
        process.terminate()
        process.wait(timeout=3)
print('PASS: exact PID, numeric FDs, foreign CLOSED socket ignored, own socket detected')
