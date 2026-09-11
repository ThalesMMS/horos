#!/usr/bin/env python3
"""Publish a synthetic Bonjour peer so a running Horos can discover it (#606).

Two controlled peers without a second machine: this process advertises one
service with DNS-SD through `dns-sd(1)`, which is part of macOS, and prints what
it published. It carries no token or secret, and it listens on nothing: the
point is discovery and resolution, not a transfer.

    python3 tools/publish-bonjour-peer.py --name HOROSPEER --type _osirixdb._tcp. --port 8781 \
        --txt AETitle=HOROSPEER --txt port=11112

Send it SIGTERM (or stop the process) to withdraw the advertisement.
"""
import argparse
import re
import signal
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--name', required=True)
parser.add_argument('--type', default='_osirixdb._tcp.')
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--txt', action='append', default=[], help='key=value, repeatable')
parser.add_argument('--seconds', type=float, default=120, help='withdraw after this long')
args = parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9 _-]{1,63}', args.name):
    parser.error('Use a plain service name')
if not re.fullmatch(r'_[a-z0-9-]+\._(tcp|udp)\.?', args.type):
    parser.error('Use a plain service type')
if not 1 <= args.port <= 65535:
    parser.error('Use a real port')
for pair in args.txt:
    key = pair.split('=', 1)[0]
    if re.search(r'token|secret|password|credential', key, re.I):
        parser.error('This peer never advertises a secret: %s' % key)

command = ['/usr/bin/dns-sd', '-R', args.name, args.type, 'local', str(args.port)] + args.txt
print('publishing: %s' % ' '.join(command), flush=True)
process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def withdraw(*_):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    print('withdrawn', flush=True)
    sys.exit(0)


signal.signal(signal.SIGTERM, withdraw)
signal.signal(signal.SIGINT, withdraw)
deadline = time.monotonic() + args.seconds
while time.monotonic() < deadline and process.poll() is None:
    line = process.stdout.readline()
    if line:
        print(line.rstrip(), flush=True)
    else:
        time.sleep(0.1)
withdraw()
