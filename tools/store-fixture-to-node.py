#!/usr/bin/env python3
"""Send a directory of DICOM files to a node with C-STORE, and say what it answered.

A receiving application answers each instance separately, and what it answers is
a promise: Success means the instance was accepted and kept. This sends every
file in a directory and prints the status that came back for each, so that
promise can be compared with what the receiver actually has afterwards.
"""
import argparse
import sys
from pathlib import Path

import pydicom
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian
from pynetdicom import AE, ALL_TRANSFER_SYNTAXES, debug_logger  # noqa: F401
from pynetdicom.sop_class import Verification

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory', type=Path, help='the files to send')
parser.add_argument('--address', default='127.0.0.1')
parser.add_argument('--port', type=int, default=11112)
parser.add_argument('--called', default='HOROSDEV', help='the receiver\'s AE title')
parser.add_argument('--calling', default='STOREFIX', help='our own AE title')
arguments = parser.parse_args()

files = sorted(path for path in arguments.directory.iterdir()
               if path.is_file() and path.suffix.lower() == '.dcm')
if not files:
    raise SystemExit('no .dcm files in %s' % arguments.directory)

datasets = [(path, pydicom.dcmread(str(path))) for path in files]

ae = AE(ae_title=arguments.calling)
ae.add_requested_context(Verification, ALL_TRANSFER_SYNTAXES)
for _, dataset in datasets:
    ae.add_requested_context(str(dataset.SOPClassUID),
                             [ExplicitVRLittleEndian, ImplicitVRLittleEndian])

association = ae.associate(arguments.address, arguments.port, ae_title=arguments.called)
if not association.is_established:
    raise SystemExit('the association was not established')

print('%-22s %-46s %s' % ('file', 'SOP class', 'status'))
refused = 0
for path, dataset in datasets:
    try:
        answer = association.send_c_store(dataset)
        status = answer.Status if 'Status' in answer else None
    except Exception as error:                                  # noqa: BLE001
        status = None
        print('%-22s %-46s raised %s' % (path.name, dataset.SOPClassUID, error))
        refused += 1
        continue
    text = '0x%04X' % status if status is not None else 'no status'
    if status not in (0x0000,):
        refused += 1
    print('%-22s %-46s %s' % (path.name, dataset.SOPClassUID, text))
    print('%-22s %-46s %s' % ('', str(dataset.SOPInstanceUID), ''))

association.release()
print()
print('%d file(s) sent, %d not answered with Success' % (len(datasets), refused))
sys.exit(0)
