#!/usr/bin/env python3
"""Open several series at once in a running Horos, through its XML-RPC port.

Opening two or more 2D viewers is the precondition for every question about
independent windows, tiling and which viewer a menu command reaches. Doing it by
hand means shift-clicking rows in the database outline, which no background
automation can do. This does it over the wire instead.

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

`--list` reads the series of a patient from the running application, so the
UIDs need not be dug out of the database by hand. Without `--list` each UID is
opened in turn and the viewers actually displayed are printed after each one,
which is what shows the preference biting: three requests, one viewer.

Nothing here writes to the database. The port is the one in the Listener
preferences (`httpXMLRPCServerPort`), 8080 by default.
"""
import argparse
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from xml.sax.saxutils import escape


def call(method, parameters, port, timeout=120):
    members = ''.join('<member><name>%s</name><value><string>%s</string></value></member>'
                      % (escape(name), escape(value)) for name, value in parameters.items())
    body = ('<?xml version="1.0"?><methodCall><methodName>%s</methodName><params><param>'
            '<value><struct>%s</struct></value></param></params></methodCall>'
            % (method, members)).encode()
    request = urllib.request.Request('http://127.0.0.1:%d/' % port, data=body,
                                     headers={'Content-Type': 'text/xml'})
    return urllib.request.urlopen(request, timeout=timeout).read().decode('utf-8', 'replace')


def error_of(answer):
    found = re.search(r'<name>error</name><value>(-?\d+)', answer)
    return found.group(1) if found else '?'


def named(answer, key):
    return re.findall(r'<name>%s</name><value>([^<]*)</value>' % key, answer)


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
                    help='send every DisplaySeries at once, from a thread each, instead of one '
                         'after another - which is what puts the loading threads on top of one '
                         'another and is the only way to ask about locks held across a load')
parser.add_argument('--repeat', type=int, default=1,
                    help='do it this many times; the later rounds switch between series that '
                         'are already open (default 1)')
arguments = parser.parse_args()

try:
    if arguments.listing:
        if not arguments.patient:
            raise SystemExit('--list needs --patient to say whose series to list')
        answer = call('DBWindowFind', {'table': 'Series', 'execute': 'Nothing',
                                       'request': "study.patientID == '%s'" % arguments.patient},
                      arguments.port)
        names = named(answer, 'name')
        uids = named(answer, 'seriesDICOMUID')
        counts = named(answer, 'numberOfImages')
        for name, uid, count in zip(names, uids, counts):
            print('%-6s %-46s %s' % (count, name[:46], uid))
        if not names:
            print('no series for patient %s (error %s)' % (arguments.patient, error_of(answer)))
        raise SystemExit(0)

    if not arguments.uids:
        raise SystemExit('give at least one SeriesInstanceUID, or --list')

    if arguments.close_first:
        call('CloseAllWindows', {}, arguments.port)

    def ask(uid):
        parameters = {'SeriesInstanceUID': uid}
        if arguments.patient:
            parameters['PatientID'] = arguments.patient
        started = time.time()
        return error_of(call('DisplaySeries', parameters, arguments.port)), time.time() - started

    for round_number in range(max(arguments.repeat, 1)):
        if arguments.concurrent:
            # Answering is not loading: DisplaySeries returns as soon as the
            # viewer exists, and the images arrive on a thread of their own. The
            # point of sending them together is to have those threads overlap.
            answers = {}
            threads = [threading.Thread(target=lambda i=i, uid=uid: answers.__setitem__(i, ask(uid)))
                       for i, uid in enumerate(arguments.uids)]
            started = time.time()
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            errors = sorted({answer for answer, _ in answers.values()})
            print('round %d: %d series asked for at once, answered in %.1f s, error(s) %s'
                  % (round_number + 1, len(arguments.uids), time.time() - started,
                     ', '.join(errors)))
        else:
            for uid in arguments.uids:
                error, elapsed = ask(uid)
                displayed = named(call('GetDisplayed2DViewerSeries', {}, arguments.port), 'name')
                print('%-22s error %-4s in %5.1f s, %d viewer(s): %s'
                      % (uid[-20:], error, elapsed, len(displayed), ', '.join(displayed)))

    displayed = named(call('GetDisplayed2DViewerSeries', {}, arguments.port), 'name')
    if len(displayed) < len(arguments.uids):
        print('\n%d series asked for, %d viewer(s) displayed: the application is closing the\n'
              'viewers it already had. Switch off CloseAllWindowsBeforeXMLRPCOpen and restart it.'
              % (len(arguments.uids), len(displayed)), file=sys.stderr)
        raise SystemExit(1)
except urllib.error.URLError as failure:
    raise SystemExit('no XML-RPC answer on port %d: %s' % (arguments.port, failure))
