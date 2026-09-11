#!/usr/bin/env python3
"""The application C-GET loop stores on its own association with request-local state."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
receiver = (root / 'Horos/Sources/HorosDIMSEGet.mm').read_bytes().decode('latin1')
node = (root / 'Horos/Sources/DCMTKQueryNode.mm').read_bytes().decode('latin1')


def body(signature, source):
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


# --- the target compiles the implementation that handles sub-operations -------
if 'HorosDIMSEGet.mm in Sources' not in project:
    failures.append('dimget.mm is not compiled: the C-GET that reaches the network would be '
                    'the unadapted C-MOVE copy in dimget.cc, and every retrieval would fail '
                    'with every instance counted as failed')
if re.search(r'dimget\.cc in Sources', project):
    failures.append('dimget.cc is compiled as well: two definitions of DIMSE_getUser, and which '
                    'one the link picks is not something to leave to chance')

# --- and that implementation really does handle them --------------------------
loop = body('HorosDIMSEGetUser(', receiver)
if not loop:
    failures.append('DIMSE_getUser is gone from dimget.mm')
else:
    if 'DIMSE_C_STORE_RQ' not in loop:
        failures.append('the C-GET loop no longer accepts a C-STORE-RQ on the association, so a '
                        'conformant peer\'s sub-operations are rejected as unexpected responses')
    if 'HorosStoreSCP(assoc,' not in loop or 'mainStoreSCP' in loop:
        failures.append('C-GET must use its own storage context instead of a listener global')
    for setup in ('factory.createDBHandle(', 'storageOptions.dimse_timeout_ = timeout', 'storageOptions.blockMode_ = blockMode'):
        if setup not in loop: failures.append('missing per-request storage setup: '+setup)
    if 'initiateImportFilesFromIncomingDirUnlessAlreadyImporting' not in loop:
        failures.append('nothing asks the database to index what arrived, so a retrieval that '
                        'finished can still show nothing')
    if 'DIMSE_C_GET_RSP' not in loop:
        failures.append('the C-GET responses themselves are no longer read')

# --- a retrieval that loses instances says so ---------------------------------
get = body('- (OFCondition)getSCU:', node)
if not get:
    failures.append('-getSCU:network:dataset: is gone')
else:
    if 'NumberOfFailedSubOperations' not in get:
        failures.append('the retrieval does not look at the failed sub-operation count, so a '
                        'partial C-GET is reported as a success')
    # The sentence itself lives in HorosRetrieveCompletion, which the C-MOVE path
    # shares; tests/test-cmove-completeness.py holds it to its wording.
    for field in ('HorosRetrieveCompletion', 'everythingArrived', 'completion.summary'):
        if field not in get:
            failures.append('the incomplete-retrieval message does not go through %s' % field)
    if 'Get Failed' not in get:
        failures.append('an incomplete retrieval is not reported to the user at all')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the compiled C-GET stores the sub-operations that arrive on its own association and '
      'names what an incomplete retrieval lost')
