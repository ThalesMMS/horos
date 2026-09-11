#!/usr/bin/env python3
"""Verify the ten-UID C-GET omission/duplicate/identity-mismatch fixture."""
import argparse,json,re,sqlite3
from collections import Counter
from pathlib import Path
import numpy as np,pydicom
p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('peer',type=Path);p.add_argument('--baseline',action='store_true');p.add_argument('--retry',action='store_true');a=p.parse_args()
s=json.loads((a.peer/'cget-negotiation.json').read_text());by_number={int(x['number']):x for x in s['instances']};assert len(by_number)==10
expected={x['sopInstance']:x for x in by_number.values()}
if a.retry:
 requests=s['retrievals'];assert len(requests)==2
 retry=requests[-1];assert retry['level']=='IMAGE' and set(retry['requestedUIDs'])=={by_number[i]['sopInstance'] for i in (9,10)}
 assert len(retry['sentPlan'])==2
 received={str(pydicom.dcmread(f).SOPInstanceUID) for f in (a.run/'db').rglob('*.dcm')}
 assert received==expected.keys()
 with sqlite3.connect(f"file:{a.run/'db/Horos Data/Database.sql'}?mode=ro",uri=True) as c:frames=c.execute('select count(*) from ZIMAGE').fetchone()[0]
 assert frames==17
 print(json.dumps({'requestLevel':'IMAGE','requestedInstanceNumbers':[9,10],'sent':2,'finalUniqueUIDs':10,'indexedFrames':frames},indent=2))
 raise SystemExit(0)
responses=[x for x in s['timeline'] if x['event']=='C_STORE_RSP'];assert len(responses)==10
counts=Counter(x['AffectedSOPInstanceUID'] for x in responses)
assert counts[by_number[1]['sopInstance']]==2 and by_number[10]['sopInstance'] not in counts
rejected={x['AffectedSOPInstanceUID'] for x in responses if int(x['Status'])!=0}
assert rejected==(set() if a.baseline else {by_number[9]['sopInstance']})
if not a.baseline:assert next(int(x['Status']) for x in responses if int(x['Status'])!=0)==0xa900
received={};unknown=[]
for f in (a.run/'db').rglob('*.dcm'):
 ds=pydicom.dcmread(f);uid=str(ds.SOPInstanceUID)
 if uid not in expected:unknown.append(uid);assert a.baseline and np.all(ds.pixel_array==9);continue
 assert np.all(ds.pixel_array==expected[uid]['number'])
 received[uid]=int(getattr(ds,'NumberOfFrames',1))
assert set(expected)-received.keys()=={by_number[i]['sopInstance'] for i in (9,10)}
assert len(unknown)==int(a.baseline)
log=(a.run/'horos.log').read_text(errors='replace')
assert 'CGET_INDEPENDENT_WATCHDOG running=0' in log
reported=10 if a.baseline else 9
assert f'received={reported} expected=10 cancelled=0' in log
if not a.baseline:assert 'CGET_NOTICE main=1' in log and 'C-GET incomplete:' in log
# Horos indexes a multiframe object as multiple image rows; do not equate rows to instances.
db=a.run/'db/Horos Data/Database.sql'
with sqlite3.connect(f'file:{db}?mode=ro',uri=True) as c:rows=c.execute('select count(*) from ZIMAGE').fetchone()[0]
assert rows==sum(received.values())+len(unknown),(rows,received)
print(json.dumps({'expectedUIDs':10,'validUniqueUIDs':len(received),'missingInstanceNumbers':[9,10],
 'duplicateInstanceNumbers':[1],'rejectedInstanceNumbers':[] if a.baseline else [9],
 'unexpectedUIDs':len(unknown),'reportedCompletedSuboperations':reported,'indexedFrames':rows},indent=2))
