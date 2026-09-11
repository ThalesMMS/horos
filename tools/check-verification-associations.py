#!/usr/bin/env python3
"""Compare actual C-ECHO/C-FIND association records from the loopback recorder."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('record', type=Path)
parser.add_argument('--verify-index', type=int, default=0)
parser.add_argument('--query-index', type=int, default=1)
args = parser.parse_args()
records = json.loads(args.record.read_text())['associations']
verify, query = records[args.verify_index], records[args.query_index]
for key in ('implementationClassUID', 'implementationVersionName', 'callingAETitle', 'calledAETitle'):
    assert verify[key] and verify[key] == query[key], f'{key}: verify={verify[key]!r}, query={query[key]!r}'
assert any(op['operation'] == 'C-ECHO' and op['status'] == '0x0000' for op in verify['operations'])
assert any(op['operation'] == 'C-FIND' for op in query['operations'])
assert any(c['accepted'] and c['abstractSyntax'] == '1.2.840.10008.1.1' for c in verify['contexts'])
assert any(c['accepted'] and c['abstractSyntax'] == '1.2.840.10008.5.1.4.1.2.2.1' for c in query['contexts'])
print('matched:', verify['implementationClassUID'], verify['implementationVersionName'],
      verify['callingAETitle'], '->', verify['calledAETitle'])
