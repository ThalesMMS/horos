#!/usr/bin/env python3
"""The shared-database client runs on the native transport (#607).

Source level, with `<git revision>` as an optional argument for the negative
control:

* `RemoteDicomDatabase` sends through `HorosDatabaseTransport`, not through
  `N2Connection`'s thread-and-run-loop-per-request;
* an Objective-C exception raised by a streaming handler is turned into an
  error before it can cross into Swift, and a failed request raises with the
  transport's own description;
* the five-attempt replay of *every* request is gone: only requests the
  command classification calls idempotent are sent again, and only after the
  partial local state of an index or a download has been discarded;
* a command that changes the remote database is never replayed, and its
  failure says what the operator has to do;
* waiting for a connection slot observes cancellation instead of blocking
  forever;
* the inbound server, the N2 classes and the other transports are untouched.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def read(path):
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


client = read('Horos/Sources/RemoteDicomDatabase.mm')
failures = []


def method(source, signature, terminator='\n}\n'):
    start = source.find(signature)
    if start < 0:
        return ''
    return source[start:source.find(terminator, start) + len(terminator)]


send = method(client, 'static NSData *HorosSendDatabaseRequest(')
if 'HorosDatabaseTransport sendRequest:' not in send:
    failures.append('the client does not send through the native transport')
if '@try { return handler(data); }' not in send or 'HorosDatabaseResponse' not in send:
    failures.append('an Objective-C exception from a handler can cross into Swift')
if 'thread.isCancelled' not in send:
    failures.append('the transport is not told about cancellation')

request = method(client, '-(NSData*)synchronousRequest:(NSData*)request urgent:(BOOL)urgent dataHandlerTarget:(id)target selector:(SEL)sel context:(void*)context {')
if 'N2Connection sendSynchronousRequest:' in request:
    failures.append('the client still uses the legacy thread-per-request path')
if 'HorosSharedDatabaseCommand isRetryableRequest:' not in request:
    failures.append('requests are not classified before being sent again')
if 'actionRequiredForRequest:' not in request:
    failures.append('a failed mutation does not say what the operator must do')
if not re.search(r'attempts = \[HorosSharedDatabaseCommand isRetryableRequest: request\] \? \d+ : 1', request):
    failures.append('a request that is not idempotent may still be attempted more than once')
if 'HorosResetRemoteDownload' not in request or 'setUnsignedIntegerValue:0' not in request:
    failures.append('a retry does not discard the partial local state of a download or an index')
if 'DISPATCH_TIME_FOREVER' in request:
    failures.append('waiting for a connection slot still blocks forever')
if 'isCancelled' not in request:
    failures.append('waiting for a connection slot does not observe cancellation')

# The inbound server and the other transports are out of scope.
for path, forbidden in (('Horos/Sources/BonjourPublisher.m', 'N2ConnectionListener'),
                        ('Nitrogen/Sources/N2Connection.h', 'sendSynchronousRequest:')):
    if forbidden not in read(path):
        failures.append('%s no longer has %s; the inbound server and N2 API are out of scope' % (path, forbidden))

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: the shared-database client uses the native transport, classifies retries and stays cancellable')
