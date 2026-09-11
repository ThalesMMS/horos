#!/usr/bin/env python3
"""A C-STORE SCP that refuses in the three ways a send can fail, and says which.

A successful C-ECHO says nothing about which SOP classes and transfer syntaxes a
node will accept, which is the whole difficulty behind "DIMSE inappropriate data
for message". This accepts a chosen set of SOP classes only, so anything else
finds no presentation context; refuses named instances with a chosen DIMSE
status; and records every association and every C-STORE, so what the sender was
told can be compared against what it reported.
"""
import argparse
import json
import threading
import time
from pathlib import Path

from pynetdicom import AE, ALL_TRANSFER_SYNTAXES, evt
from pynetdicom.sop_class import Verification

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence', type=Path, help='directory for the result file')
parser.add_argument('--port', type=int, default=11181)
parser.add_argument('--aetitle', default='STOREFIX')
parser.add_argument('--accept', action='append', default=[],
                    help='a SOP class UID to accept; repeatable. Default: CT Image Storage')
parser.add_argument('--refuse-instance', action='append', default=[],
                    help='a SOP Instance UID to answer with --refuse-status; repeatable')
parser.add_argument('--refuse-status', type=lambda v: int(v, 0), default=0xA700,
                    help='the DIMSE status for refused instances (default 0xA700, out of resources)')
parser.add_argument('--store-to', type=Path, default=None,
                    help='write accepted instances here; by default they are only counted')
parser.add_argument('--store-delay', type=float, default=0, help='delay each response to exercise overlapping sends')
args = parser.parse_args()
if not 0 <= args.store_delay <= 5: parser.error('store delay must be between 0 and 5 seconds')
if not 1024 <= args.port <= 65535:
    parser.error('Use an unprivileged port')
accepted = args.accept or ['1.2.840.10008.5.1.4.1.1.2']  # CT Image Storage
if args.store_to:
    args.store_to.mkdir(parents=True, exist_ok=True)

args.evidence.mkdir(parents=True, exist_ok=True)
state = {'aetitle': args.aetitle, 'port': args.port, 'accepted_sop_classes': accepted,
         'refused_instances': args.refuse_instance, 'refuse_status': args.refuse_status,
         'associations': [], 'stored': [], 'refused': []}
lock = threading.Lock()


def save():
    with lock:
        (args.evidence / 'store-results.json').write_text(json.dumps(state, indent=2) + '\n')


save()


def handle_open(event):
    proposed = []
    for context in event.assoc.requestor.requested_contexts:
        proposed.append({'abstract_syntax': str(context.abstract_syntax),
                         'transfer_syntaxes': [str(ts) for ts in context.transfer_syntax]})
    with lock:
        state['associations'].append({
            'calling_aetitle': event.assoc.requestor.ae_title,
            'accepted_at': time.monotonic(),
            # What the peer says it is. This is the only place the DICOM
            # toolkit a sender was built with is visible from outside it.
            'implementation_class_uid': str(event.assoc.requestor.implementation_class_uid or ''),
            'implementation_version_name': (event.assoc.requestor.implementation_version_name
                                            or b'').decode('ascii', 'replace')
            if isinstance(event.assoc.requestor.implementation_version_name, bytes)
            else str(event.assoc.requestor.implementation_version_name or ''),
            'maximum_pdu_length': event.assoc.requestor.maximum_length,
            'proposed': proposed,
            'accepted': [str(c.abstract_syntax) for c in event.assoc.accepted_contexts]})
    save()


def handle_store(event):
    ds = event.dataset
    ds.file_meta = event.file_meta
    record = {'received_at': time.monotonic(), 'sop_class': str(getattr(ds, 'SOPClassUID', '')),
              'sop_instance': str(getattr(ds, 'SOPInstanceUID', '')),
              'transfer_syntax': str(event.context.transfer_syntax),
              'series': str(getattr(ds, 'SeriesInstanceUID', '')),
              'study': str(getattr(ds, 'StudyInstanceUID', ''))}
    if args.store_delay: time.sleep(args.store_delay)
    if record['sop_instance'] in args.refuse_instance:
        with lock:
            record['status'] = '0x%04X' % args.refuse_status
            state['refused'].append(record)
        save()
        return args.refuse_status
    if args.store_to:
        ds.save_as(args.store_to / (record['sop_instance'] + '.dcm'), enforce_file_format=True)
    with lock:
        record['status'] = '0x0000'
        state['stored'].append(record)
    save()
    return 0x0000


ae = AE(ae_title=args.aetitle)
ae.add_supported_context(Verification, ALL_TRANSFER_SYNTAXES)
for sop_class in accepted:
    ae.add_supported_context(sop_class, ALL_TRANSFER_SYNTAXES)
print('store SCP %s on %d, accepting %s' % (args.aetitle, args.port, ', '.join(accepted)), flush=True)
ae.start_server(('127.0.0.1', args.port), block=True,
                evt_handlers=[(evt.EVT_C_STORE, handle_store), (evt.EVT_ACCEPTED, handle_open)])
