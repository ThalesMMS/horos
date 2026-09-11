#!/usr/bin/env python3
"""Compare native UID-list query results with the recording synthetic SCP."""
import argparse
import json
from pathlib import Path
import re

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('server_record', type=Path)
p.add_argument('app_log', type=Path)
a = p.parse_args()
record = json.loads(a.server_record.read_text())
uids = record['studies']
assert len(uids) == 4
missing = '1.2.826.0.1.3680043.10.543.169.999'
requested = [[uids[0], uids[1]], [uids[2], missing], [uids[0], uids[2], uids[3]]]
expected = [requested[0], [uids[2]], requested[2]]
assert len(record['queries']) == 3, record['queries']
log = a.app_log.read_text(errors='replace')
for index, (query, ask, answer) in enumerate(zip(record['queries'], requested, expected)):
    assert query['level'] == 'STUDY'
    assert query['elements']['StudyInstanceUID'] == ask, query
    assert set(query['answers']) == set(answer), query
    marker = 'UID_LIST_FIELD_RESULT ' + str(index) if index < 2 else 'UID_LIST_URL_RESULT'
    match = re.search(re.escape(marker) + r'\s+\((.*?)\)', log, re.S)
    assert match, marker
    received = re.findall(r'"([0-9.]+)"', match[1])
    assert len(received) == len(answer) and set(received) == set(answer), received
    print('%s: %d values on wire, %d exact native results' % (marker, len(ask), len(received)))
assert 'UID_LIST_DISPATCH_DONE' in log
