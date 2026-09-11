#!/usr/bin/env python3
"""Open, abort and time out Web Portal connections in parallel, and see what is left.

The stack behind #259 is a close path: CFRelease(NULL) and CFHash(NULL) while
streams are being closed and unscheduled. What produces it, if anything, is
concurrency - a connection closing while another thread is still touching its
streams - so this opens many at once and drops them at every stage: before
sending anything, after half a request line, after the headers, and while the
body is still arriving.

    python3 tools/stress-web-portal-connections.py --port 13180 --rounds 20

It reports the process's open file descriptors before and after, which is where a
stream that was never closed shows up.
"""
import argparse, random, socket, subprocess, sys, threading, time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--port', type=int, default=13180)
parser.add_argument('--rounds', type=int, default=20)
parser.add_argument('--parallel', type=int, default=24)
parser.add_argument('--pid', type=int, help='the server process, to count descriptors')
parser.add_argument('--path', default='/main', help='a path the server answers')
options = parser.parse_args()


def descriptors(pid):
    if not pid:
        return None
    done = subprocess.run(['lsof', '-p', str(pid)], capture_output=True, text=True)
    return sum(1 for line in done.stdout.splitlines()[1:] if line.strip())


STAGES = ('connect-and-drop', 'half-request', 'headers-then-drop',
          'body-then-drop', 'complete', 'slow-headers', 'reset')
counts = {stage: 0 for stage in STAGES}
errors = []
lock = threading.Lock()


def one(stage):
    try:
        sock = socket.create_connection((options.host, options.port), timeout=5)
        try:
            if stage == 'connect-and-drop':
                pass
            elif stage == 'half-request':
                sock.sendall(b'GET /ma')
            elif stage == 'headers-then-drop':
                sock.sendall(f'GET {options.path} HTTP/1.1\r\nHost: x\r\n'.encode())
            elif stage == 'body-then-drop':
                sock.sendall(f'POST {options.path} HTTP/1.1\r\nHost: x\r\n'
                             f'Content-Length: 4096\r\n\r\n'.encode() + b'a' * 32)
            elif stage == 'complete':
                sock.sendall(f'GET {options.path} HTTP/1.1\r\nHost: x\r\n'
                             f'Connection: close\r\n\r\n'.encode())
                while sock.recv(65536):
                    pass
            elif stage == 'slow-headers':
                sock.sendall(f'GET {options.path} HTTP/1.1\r\n'.encode())
                for header in (b'Host: x\r\n', b'Accept: */*\r\n', b'Connection: close\r\n'):
                    time.sleep(0.05)
                    sock.sendall(header)
                sock.sendall(b'\r\n')
                sock.recv(4096)
            elif stage == 'reset':
                # A hard reset, so the server sees the connection vanish mid-flight.
                sock.sendall(f'GET {options.path} HTTP/1.1\r\nHost: x\r\n\r\n'.encode())
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                __import__('struct').pack('ii', 1, 0))
        finally:
            sock.close()
        with lock:
            counts[stage] += 1
    except Exception as exception:          # a refused or reset connection is a result too
        with lock:
            errors.append(f'{stage}: {exception!r}')


before = descriptors(options.pid)
started = time.time()
for round_number in range(options.rounds):
    threads = [threading.Thread(target=one, args=(random.choice(STAGES),))
               for _ in range(options.parallel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
elapsed = time.time() - started
time.sleep(3)                                # let the server finish closing
after = descriptors(options.pid)

print(f'{options.rounds * options.parallel} connections in {elapsed:.1f}s')
for stage in STAGES:
    print(f'  {stage:20s} {counts[stage]}')
if errors:
    print(f'  {len(errors)} connection error(s), first few:')
    for message in errors[:5]:
        print(f'    {message}')
if before is not None:
    print(f'open file descriptors: {before} before, {after} after')
alive = subprocess.run(['kill', '-0', str(options.pid)], capture_output=True) if options.pid else None
if options.pid:
    print('server still running' if alive.returncode == 0 else 'SERVER IS GONE')
    sys.exit(0 if alive.returncode == 0 else 1)
