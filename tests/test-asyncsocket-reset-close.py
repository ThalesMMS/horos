#!/usr/bin/env python3
"""A reset between accept and stream open must not leave a CLOSED descriptor.

#259 is the Web Portal close path: CFRelease(NULL) is already gone, but a peer
that vanishes while CFStream is still opening leaves the copy of the accepted
descriptor that CFStream never took. The next close is supposed to happen when
that stream gives up, not by closing the listen socket's number from -close.

This compiles production AsyncSocket.m with the address and undefined-behaviour
sanitizers, accepts on loopback, and repeats the hard reset the portal stress
tool uses (SO_LINGER 0 after a short GET). After the batch the helper must still
be running, sanitizers must stay silent, and lsof must not show a CLOSED TCP
socket per reset.
"""
from pathlib import Path
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

root = Path(__file__).resolve().parents[1]
failures = []

HELPER = r'''
#import "AsyncSocket.h"
#import <Foundation/Foundation.h>

@interface Listener : NSObject
{
    NSMutableArray *clients;
}
@end

@implementation Listener

- (id)init
{
    if ((self = [super init]))
        clients = [[NSMutableArray alloc] init];
    return self;
}

- (void)dealloc
{
    [clients release];
    [super dealloc];
}

- (void)onSocket:(AsyncSocket *)sock didAcceptNewSocket:(AsyncSocket *)newSocket
{
    [clients addObject:newSocket];
}

- (void)onSocket:(AsyncSocket *)sock didConnectToHost:(NSString *)host port:(UInt16)port
{
#pragma unused(host, port)
    [sock readDataWithTimeout:2 tag:0];
}

- (void)onSocket:(AsyncSocket *)sock didReadData:(NSData *)data withTag:(long)tag
{
#pragma unused(data, tag)
    NSData *reply = [@"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"
                     dataUsingEncoding:NSUTF8StringEncoding];
    [sock writeData:reply withTimeout:-1 tag:0];
    [sock disconnectAfterWriting];
}

- (void)onSocketDidDisconnect:(AsyncSocket *)sock
{
    [clients removeObject:sock];
}

@end

int main(void)
{
    NSAutoreleasePool *pool = [[NSAutoreleasePool alloc] init];
    Listener *listener = [[Listener alloc] init];
    AsyncSocket *server = [[AsyncSocket alloc] initWithDelegate:listener];
    NSError *error = nil;
    if (![server acceptOnInterface:@"localhost" port:0 error:&error])
    {
        fprintf(stderr, "listen failed: %s\n", [[error description] UTF8String]);
        return 1;
    }
    printf("PORT %u\n", (unsigned)[server localPort]);
    fflush(stdout);
    [[NSRunLoop currentRunLoop] run];
    [server release];
    [listener release];
    [pool drain];
    return 0;
}
'''


def closed_tcp(pid):
    done = subprocess.run(['lsof', '-p', str(pid), '-nP', '-iTCP'],
                          capture_output=True, text=True)
    return sum(1 for line in done.stdout.splitlines() if '(CLOSED)' in line)


def descriptors(pid):
    done = subprocess.run(['lsof', '-p', str(pid)], capture_output=True, text=True)
    return max(0, len([line for line in done.stdout.splitlines() if line.strip()]) - 1)


def reset_one(host, port):
    sock = socket.create_connection((host, port), timeout=5)
    try:
        sock.sendall(b'GET /index.html HTTP/1.1\r\nHost: x\r\n\r\n')
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
    finally:
        sock.close()


def complete_one(host, port):
    sock = socket.create_connection((host, port), timeout=5)
    try:
        sock.sendall(b'GET /index.html HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
        while sock.recv(65536):
            pass
    finally:
        sock.close()


with tempfile.TemporaryDirectory(prefix='horos-asyncsocket-reset-') as tmp:
    work = Path(tmp)
    (work / 'main.m').write_text(HELPER)
    built = subprocess.run(
        ['xcrun', 'clang', '-fno-objc-arc', '-fobjc-exceptions', '-g',
         '-fsanitize=address,undefined',
         '-Wno-deprecated-declarations', '-Wno-objc-method-access',
         '-I', str(root / 'cocoahttpserver'),
         str(work / 'main.m'), str(root / 'cocoahttpserver/AsyncSocket.m'),
         '-framework', 'Foundation', '-framework', 'CoreServices',
         '-o', str(work / 'helper')],
        capture_output=True, text=True)
    if built.returncode != 0:
        sys.stderr.write(built.stderr[-4000:])
        raise SystemExit('failed to compile AsyncSocket helper')

    env = dict(os.environ)
    env['ASAN_OPTIONS'] = 'abort_on_error=1:detect_leaks=0:halt_on_error=1'
    env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    server = subprocess.Popen(
        [str(work / 'helper')],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    port = None
    try:
        line = server.stdout.readline()
        if line.startswith('PORT '):
            port = int(line.split()[1])
        if not port:
            time.sleep(0.2)
            err = server.stderr.read() if server.poll() is not None else ''
            raise SystemExit('helper did not publish a port: %s %s' % (line, err))

        time.sleep(0.2)
        before_closed = closed_tcp(server.pid)
        before_fds = descriptors(server.pid)

        errors = []
        for _ in range(8):
            try:
                complete_one('127.0.0.1', port)
            except Exception as exception:
                errors.append(repr(exception))

        def run_resets(count):
            for _ in range(count):
                try:
                    reset_one('127.0.0.1', port)
                except OSError:
                    pass
                except Exception as exception:
                    errors.append(repr(exception))

        threads = [threading.Thread(target=run_resets, args=(20,)) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        # The descriptors are released some time after the resets, and how long
        # that takes depends on how busy the machine is - a fixed pause read a
        # still-draining process as a leak whenever something else was running.
        # Wait for the counts to come back instead, with a bound that is far
        # longer than the work. A real leak never settles, so this still fails
        # on one; only the timing sensitivity goes away.
        CLOSED_ALLOWED, FDS_ALLOWED, SETTLE_LIMIT = 2, 8, 30.0
        deadline = time.monotonic() + SETTLE_LIMIT
        samples = []
        while True:
            after_closed = closed_tcp(server.pid)
            after_fds = descriptors(server.pid)
            leaked_closed = after_closed - before_closed
            leaked_fds = after_fds - before_fds
            samples.append((round(time.monotonic() - (deadline - SETTLE_LIMIT), 2),
                            leaked_closed, leaked_fds))
            settled = leaked_closed <= CLOSED_ALLOWED and leaked_fds <= FDS_ALLOWED
            if settled or server.poll() is not None or time.monotonic() >= deadline:
                break
            time.sleep(0.25)

        if server.poll() is not None:
            failures.append('helper died under reset (exit %s): %s' % (
                server.returncode, server.stderr.read()[-2000:]))
        if leaked_closed > CLOSED_ALLOWED:
            failures.append(
                'hard reset left %d CLOSED TCP sockets after %.0fs (fds %d -> %d); '
                'CFStream still holds the accepted descriptor it never opened; '
                'samples (s, closed, fds): %s'
                % (leaked_closed, SETTLE_LIMIT, before_fds, after_fds, samples[-6:]))
        if leaked_fds > FDS_ALLOWED:
            failures.append('open descriptors grew by %d after %.0fs (%d -> %d); '
                            'samples (s, closed, fds): %s'
                            % (leaked_fds, SETTLE_LIMIT, before_fds, after_fds, samples[-6:]))
        if errors:
            failures.append('%d client error(s), first: %s' % (len(errors), errors[0]))

        print('resets=40 completes=8 closed %d -> %d fds %d -> %d settled in %.2fs'
              % (before_closed, after_closed, before_fds, after_fds, samples[-1][0]))
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        stderr = server.stderr.read() if server.stderr else ''
        if 'ERROR:' in stderr or 'AddressSanitizer' in stderr or 'UndefinedBehaviorSanitizer' in stderr:
            failures.append('sanitizer: %s' % stderr[-2000:])

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    raise SystemExit(1)
print('PASS: reset-during-open frees CFStream descriptors; sanitizers silent')
