#!/usr/bin/env python3
"""Open several series at once in a running Horos, through its XML-RPC port.

Opening two or more 2D viewers is the precondition for questions about independent
windows, tiling and which viewer a menu command reaches. This helper submits
openings through the existing XML-RPC interface.

The trap is one preference. `_onMainThreadOpenObjectsWithIDs:` starts with

    if( [[NSUserDefaults standardUserDefaults] boolForKey: @"CloseAllWindowsBeforeXMLRPCOpen"])
        [ViewerController closeAllWindows];

and `DefaultsOsiriX.m` registers that key as 1. So with the factory settings
every `DisplaySeries` call closes the viewers already open and you are left with
exactly one, however many series you ask for - which looks like a viewer being
reused and is not. The preference is the checkbox "Automatically close all 2D
Viewers before displaying studies with XML-RPC orders" in the Listener pane.
Turn it off in the *application's* defaults domain and restart it first:

    defaults write <bundle id> CloseAllWindowsBeforeXMLRPCOpen -bool NO

    python3 tools/open-series-xmlrpc.py --list --patient VOL-102
    python3 tools/open-series-xmlrpc.py --patient VOL-102 <uid> <uid> <uid>

`--list` reads the series of a patient from the running application. Otherwise,
DisplaySeries acknowledges acceptance asynchronously, possibly before a modal
ends or a viewer exists. After each round this helper waits up to --wait-timeout
seconds for all requested UIDs to appear in GetDisplayed2DViewerSeries. Seeing a
series there does not prove that all its pixels have finished loading.

The port is the one in the Listener preferences (`httpXMLRPCServerPort`), 8080
by default. The helper sends existing listing/viewer commands to that instance.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import math
import time
import urllib.request
import xmlrpc.client
from xml.parsers.expat import ExpatError


def call(method, parameters, port, timeout=120):
    body = xmlrpc.client.dumps((parameters,), methodname=method).encode()
    request = urllib.request.Request('http://127.0.0.1:%d/' % port, data=body,
                                     headers={'Content-Type': 'text/xml'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        try:
            values, _ = xmlrpc.client.loads(response.read())
        except (ExpatError, xmlrpc.client.Error, ValueError) as failure:
            raise RuntimeError('%s: invalid XML-RPC response (%s)' %
                               (method, type(failure).__name__)) from failure
    if len(values) != 1 or not isinstance(values[0], dict):
        raise RuntimeError('%s: expected one response dictionary' % method)
    answer = values[0]
    if str(answer.get('error')) != '0':
        raise RuntimeError('%s returned error %s' % (method, answer.get('error', '(missing)')))
    return answer


def elements(answer):
    rows = answer.get('elements')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError('XML-RPC response has no valid elements array')
    return rows


def wait_for_series(uids, port, timeout):
    deadline = time.monotonic() + timeout
    missing = set(uids)
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            displayed = elements(call('GetDisplayed2DViewerSeries', {}, port,
                                      timeout=max(0.001, remaining)))
        except TimeoutError:
            break
        observed = [row.get('seriesDICOMUID') for row in displayed]
        if any(not isinstance(uid, str) for uid in observed):
            raise RuntimeError('Displayed series response has an invalid seriesDICOMUID')
        missing = set(uids) - set(observed)
        if not missing:
            return displayed
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    raise RuntimeError('Opening was not observed within %.2f s; missing SeriesInstanceUID(s): %s. '
                       'Inspect the application for pending loading/modal UI or opening preferences '
                       '(including CloseAllWindowsBeforeXMLRPCOpen); no cause is established by this timeout.'
                       % (timeout, ', '.join(sorted(missing))))


parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('uids', nargs='*', help='SeriesInstanceUID values, in the order to open them')
parser.add_argument('--patient', default='',
                    help='PatientID (0010,0020); optional - a SeriesInstanceUID is enough to '
                         'open one, and a study with no PatientID can only be opened that way')
parser.add_argument('--port', type=int, default=8080)
parser.add_argument('--list', action='store_true', dest='listing',
                    help='print the series of that patient instead of opening anything')
parser.add_argument('--close-first', action='store_true',
                    help='send CloseAllWindows before the first series')
parser.add_argument('--concurrent', action='store_true',
                    help='submit DisplaySeries requests concurrently (up to 32 requests at once)')
parser.add_argument('--repeat', type=int, default=1,
                    help='do it this many times; the later rounds switch between series that '
                         'are already open (default 1)')
parser.add_argument('--wait-timeout', type=float, default=120,
                    help='seconds to wait for requested UIDs after each round of ACKs (default 120)')
arguments = parser.parse_args()
if not math.isfinite(arguments.wait_timeout) or arguments.wait_timeout <= 0:
    parser.error('--wait-timeout must be finite and greater than zero')

try:
    if arguments.listing:
        if not arguments.patient:
            raise SystemExit('--list needs --patient to say whose series to list')
        answer = call('DBWindowFind', {'table': 'Series', 'execute': 'Nothing',
                                       'request': "study.patientID == '%s'" % arguments.patient},
                      arguments.port)
        rows = elements(answer)
        for row in rows:
            name, uid, count = str(row.get('name', '')), row.get('seriesDICOMUID', ''), row.get('numberOfImages', '')
            print('%-6s %-46s %s' % (count, name[:46], uid))
        if not rows:
            print('no series for patient %s (error 0)' % arguments.patient)
        raise SystemExit(0)

    if not arguments.uids:
        raise SystemExit('give at least one SeriesInstanceUID, or --list')

    if arguments.close_first:
        call('CloseAllWindows', {}, arguments.port)

    def ask(uid):
        parameters = {'SeriesInstanceUID': uid}
        if arguments.patient:
            parameters['PatientID'] = arguments.patient
        started = time.monotonic()
        try:
            call('DisplaySeries', parameters, arguments.port)
        except (RuntimeError, OSError, http.client.HTTPException) as failure:
            raise RuntimeError('DisplaySeries %s: %s' % (uid, failure)) from failure
        return time.monotonic() - started

    for round_number in range(max(arguments.repeat, 1)):
        if arguments.concurrent:
            # Futures propagate request exceptions to the CLI, unlike failures
            # in detached worker threads that could silently lose an answer.
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=min(32, len(arguments.uids))) as executor:
                list(executor.map(ask, arguments.uids))
            print('round %d: %d requests accepted in %.1f s'
                  % (round_number + 1, len(arguments.uids), time.monotonic() - started))
        else:
            for uid in arguments.uids:
                elapsed = ask(uid)
                print('%-22s accepted in %5.1f s' % (uid[-20:], elapsed))
        displayed = wait_for_series(arguments.uids, arguments.port, arguments.wait_timeout)
        print('round %d: all %d requested UID(s) observed; %d viewer(s): %s' %
              (round_number + 1, len(set(arguments.uids)), len(displayed),
               ', '.join(str(row.get('name', '')) for row in displayed)))
except (RuntimeError, OSError, http.client.HTTPException) as failure:
    raise SystemExit('XML-RPC on port %d: %s' % (arguments.port, failure))
