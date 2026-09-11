#!/usr/bin/env python3
"""An SCP that writes down who is calling, what they asked for, and what came back.

Every association carries the requestor's Implementation Class UID and, usually,
an Implementation Version Name. For an application built on DCMTK those are
derived from the library's own version at compile time, so they are the linked
library saying its own version on the wire - which is a different kind of
evidence from reading a header in the source tree.

It also records the pair of AE titles, the address the association came from, and
every presentation context that was proposed together with whether it was
accepted - which is what tells a C-ECHO that works apart from a C-FIND that does
not, when the two are made by different clients. It answers C-ECHO, and answers
C-FIND with no matches, writing down the keys of each query it is asked.
"""
import argparse
import json
import time
import ssl
from pathlib import Path

from pynetdicom import AE, ALL_TRANSFER_SYNTAXES, evt
from pynetdicom.sop_class import (PatientRootQueryRetrieveInformationModelFind,
                                  StudyRootQueryRetrieveInformationModelFind, Verification)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence', type=Path, help='directory for the result file')
parser.add_argument('--port', type=int, default=11204)
parser.add_argument('--aetitle', default='WHOAREYOU')
parser.add_argument('--require-called-aet', action='store_true')
parser.add_argument('--echo-delay', type=float, default=0)
parser.add_argument('--echo-status', type=lambda s: int(s, 0), default=0)
parser.add_argument('--tls-cert', type=Path)
parser.add_argument('--tls-key', type=Path)
parser.add_argument('--tls-legacy', action='store_true', help='loopback fixture only: allow legacy TLS and ciphers')
arguments = parser.parse_args()

arguments.evidence.mkdir(parents=True, exist_ok=True)
record = {'associations': []}


def save():
    (arguments.evidence / 'association-identity.json').write_text(json.dumps(record, indent=1))


def describe(context, accepted):
    return {'abstractSyntax': str(context.abstract_syntax),
            'transferSyntaxes': [str(t) for t in (context.transfer_syntax
                                                  if isinstance(context.transfer_syntax, list)
                                                  else [context.transfer_syntax])],
            'accepted': accepted}


def on_established(event):
    requestor = event.assoc.requestor
    accepted = [describe(c, True) for c in event.assoc.accepted_contexts]
    rejected = [describe(c, False) for c in event.assoc.rejected_contexts]
    entry = {
        'callingAETitle': str(requestor.ae_title),
        'calledAETitle': str(event.assoc.acceptor.ae_title),
        'from': '%s:%s' % (requestor.address, requestor.port),
        'implementationClassUID': str(getattr(requestor, 'implementation_class_uid', '') or ''),
        'implementationVersionName': str(getattr(requestor, 'implementation_version_name', '') or ''),
        'maximumLength': int(getattr(requestor, 'maximum_length', 0) or 0),
        'contexts': accepted + rejected,
        'operations': [],
    }
    record['associations'].append(entry)
    save()
    print('association from %s to %s, at %s'
          % (entry['callingAETitle'], entry['calledAETitle'], entry['from']), flush=True)
    print('  Implementation Class UID   %s' % entry['implementationClassUID'], flush=True)
    print('  Implementation Version     %s' % entry['implementationVersionName'], flush=True)
    print('  maximum PDU length         %d' % entry['maximumLength'], flush=True)
    for context in entry['contexts']:
        print('  %-8s %s' % ('accepted' if context['accepted'] else 'REJECTED',
                             context['abstractSyntax']), flush=True)


def current():
    return record['associations'][-1] if record['associations'] else None


def on_echo(event):
    entry = current()
    if entry is not None:
        entry['operations'].append({'operation': 'C-ECHO', 'status': '0x%04x' % arguments.echo_status})
        save()
    if arguments.echo_delay: time.sleep(arguments.echo_delay)
    print('C-ECHO -> 0x%04x' % arguments.echo_status, flush=True)
    return arguments.echo_status


def on_find(event):
    keys = {}
    for element in event.identifier:
        if element.keyword:
            keys[element.keyword] = str(element.value)
    entry = current()
    if entry is not None:
        entry['operations'].append({'operation': 'C-FIND', 'keys': keys, 'answers': 0})
        save()
    print('C-FIND %s -> no matches'
          % ', '.join('%s=%s' % pair for pair in sorted(keys.items())), flush=True)
    yield 0x0000, None


def on_aborted(event):
    entry = current()
    if entry is not None:
        entry['operations'].append({'operation': 'ABORT',
                                    'source': str(getattr(event, 'source', ''))})
        save()
    print('association aborted', flush=True)


handlers = [(evt.EVT_ESTABLISHED, on_established), (evt.EVT_C_FIND, on_find),
            (evt.EVT_C_ECHO, on_echo), (evt.EVT_ABORTED, on_aborted)]

ae = AE(ae_title=arguments.aetitle)
ae.require_called_aet = arguments.require_called_aet
ae.add_supported_context(Verification, ALL_TRANSFER_SYNTAXES)
for model in (StudyRootQueryRetrieveInformationModelFind,
              PatientRootQueryRetrieveInformationModelFind):
    ae.add_supported_context(model, ALL_TRANSFER_SYNTAXES)

save()
print('%s listening on port %d' % (arguments.aetitle, arguments.port), flush=True)
try:
    tls_context = None
    if arguments.tls_cert:
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if arguments.tls_legacy:
            tls_context.minimum_version = ssl.TLSVersion.TLSv1
            tls_context.set_ciphers('ALL:@SECLEVEL=0')
        tls_context.load_cert_chain(arguments.tls_cert, arguments.tls_key)
    ae.start_server(('127.0.0.1', arguments.port), evt_handlers=handlers, ssl_context=tls_context)
except KeyboardInterrupt:
    pass
finally:
    save()
