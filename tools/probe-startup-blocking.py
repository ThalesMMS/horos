#!/usr/bin/env python3
"""What the main thread is doing while an application starts, second by second.

"It hangs on startup" is one sentence covering several different things: a modal
panel raised from `applicationDidFinishLaunching:`, a database opened on the main
thread, a network call with no timeout. They look identical from outside and are
told apart by one question - what is the main thread's stack right now - which is
what `sample` answers.

So this launches the application, samples the main thread on a fixed interval,
and prints the deepest frame that belongs to the application itself. A frame that
stays put across samples is a block; a frame that moves is work in progress. The
timeline separates the scenarios without guessing at any of them.

    python3 tools/probe-startup-blocking.py build/Development/HorosDevelopment.app \
        --seconds 20 -- -MOUNT 1 -STORESCP NO

Nothing here is specific to one application beyond the default bundle path: point
it at any macOS bundle and pass that application's own arguments after `--`.
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('application', type=Path, help='the .app bundle or its executable')
parser.add_argument('--seconds', type=float, default=20.0, help='how long to watch')
parser.add_argument('--interval', type=float, default=1.0, help='seconds between samples')
parser.add_argument('--log', type=Path, help='where to keep the application output')
parser.add_argument('--keep-samples', type=Path,
                    help='directory to keep every raw sample in, for the record')
parser.add_argument('arguments', nargs='*', help='arguments for the application, after --')
options = parser.parse_args()

binary = options.application
if binary.suffix == '.app':
    inside = binary / 'Contents' / 'MacOS'
    candidates = [p for p in inside.iterdir() if p.is_file() and os.access(p, os.X_OK)]
    if not candidates:
        raise SystemExit('%s has no executable in Contents/MacOS' % binary)
    binary = candidates[0]
if not os.access(binary, os.X_OK):
    raise SystemExit('%s is not executable' % binary)

# The frames every macOS application shares. Naming one of them as "what the main
# thread is doing" says nothing, so the deepest frame outside them is reported.
UNINTERESTING = re.compile(
    r'\b(start|main|NSApplicationMain|-\[NSApplication run\]|_?NSTryRunModal'
    r'|__CFRUNLOOP|CFRunLoop|_DPSNextEvent|_DPSBlockUntil|ReceiveNextEvent'
    r'|RunCurrentEventLoop|mach_msg|__psynch|__semwait|__workq|read|select|poll)')
FRAME = re.compile(r'^\s*\+?\s*\d+\s+(.*?)\s+\(in ([^)]+)\)(?:.*?\s(\S+\.(?:m|mm|c|cpp|swift):\d+))?')


def main_thread_stack(pid, keep=None):
    """The main thread's frames, outermost first, or None if it could not be read."""
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as handle:
        path = handle.name
    try:
        done = subprocess.run(['sample', str(pid), '1', '-file', path],
                              capture_output=True, timeout=60)
        if done.returncode != 0:
            return None
        text = Path(path).read_text(errors='replace')
        if keep:
            keep.write_text(text)
        lines = text.splitlines()
        started = None
        for index, line in enumerate(lines):
            if 'com.apple.main-thread' in line:
                started = index + 1
                break
        if started is None:
            return None
        frames = []
        for line in lines[started:]:
            if not line.strip():
                break
            match = FRAME.match(line)
            if not match:
                break
            symbol, image, source = match.group(1), match.group(2), match.group(3)
            frames.append((symbol.strip(), image.strip(), source))
        return frames
    finally:
        Path(path).unlink(missing_ok=True)


def short(symbol):
    """`-[AppController applicationDidFinishLaunching:]` reads better as its selector."""
    match = re.match(r'^[-+]\[\w+ (.+)\]$', symbol)
    return match.group(1) if match else symbol


def describe(frames, application, depth=3):
    """The application's own frames at the bottom of the stack, and what they called.

    Its own frames are what distinguishes one startup block from another; the
    system frames underneath are the same wait in every case, so only the first
    interesting one is kept, to say what kind of wait it is.
    """
    if not frames:
        return 'could not be sampled'
    own = [index for index, frame in enumerate(frames) if frame[1] == application]
    if not own:
        return 'nothing of its own on the stack (%s)' % frames[-1][0]
    chain = [frames[index] for index in own[-depth:]]
    if len(chain) == 1 and chain[0][0] == 'main':
        return 'idle in the event loop'
    text = ' -> '.join(short(symbol) for symbol, _, _ in chain)
    source = chain[-1][2]
    if source:
        text += ' (%s)' % source
    after = [frames[index][0] for index in range(own[-1] + 1, len(frames))]
    interesting = [symbol for symbol in after if not UNINTERESTING.search(symbol)]
    if interesting:
        text += ' -> ' + interesting[0]
    return text


log = options.log or Path(tempfile.mkdtemp(prefix='startup-')) / 'application.log'
log.parent.mkdir(parents=True, exist_ok=True)
if options.keep_samples:
    options.keep_samples.mkdir(parents=True, exist_ok=True)

environment = dict(os.environ)
with log.open('wb') as output:
    process = subprocess.Popen([str(binary)] + options.arguments,
                               stdout=output, stderr=subprocess.STDOUT, env=environment)

print('%s [%d], watching for %.0f s' % (binary.name, process.pid, options.seconds), flush=True)
print('output: %s' % log, flush=True)
started = time.time()
timeline = []
try:
    while time.time() - started < options.seconds:
        moment = time.time() - started
        if process.poll() is not None:
            print('t=%5.1fs  the application exited (%s)' % (moment, process.returncode))
            break
        keep = (options.keep_samples / ('sample-%05.1f.txt' % moment)) if options.keep_samples else None
        frames = main_thread_stack(process.pid, keep)
        where = describe(frames, binary.name)
        timeline.append((moment, where))
        print('t=%5.1fs  %s' % (moment, where), flush=True)
        time.sleep(options.interval)
finally:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

print()
print('how long the main thread stayed in each place')
runs = []
for moment, where in timeline:
    if runs and runs[-1][0] == where:
        runs[-1][2] = moment
    else:
        runs.append([where, moment, moment])
for where, first, last in runs:
    print('  %5.1f s  %s' % (last - first + options.interval, where))
