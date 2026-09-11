#!/usr/bin/env python3
"""Verify native listener-free C-GET objects, frames, roles and terminal signals."""
import argparse,json,re,sqlite3
from pathlib import Path
import pydicom,numpy as np
p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('peer',type=Path);p.add_argument('--mode',choices=['complete','failure','cancel','cancel-before-first'],default='complete');a=p.parse_args()
assert 'local-validation' in a.run.resolve().parts
log=(a.run/'horos.log').read_text(errors='replace');peer=json.loads((a.peer/'cget-negotiation.json').read_text())
assert 'CGET_REAL_LISTENER available=0' in log
assert 'CGET_INDEPENDENT_WATCHDOG running=0' in log and 'CGET_INDEPENDENT_WATCHDOG running=1' not in log
assert 'CGET_INDEPENDENT_EXCEPTION' not in log and 'scp == nil' not in log
end=re.search(r'CGET_INDEPENDENT_END operation0 ([\d.]+) received=(\d+) expected=(\d+) cancelled=(\d)',log);assert end
count=int(end[2]);expected={x['sopInstance']:x for x in peer['instances']};received={}
for f in (a.run/'db').rglob('DATABASE.noindex/**/*.dcm'):
 ds=pydicom.dcmread(f);uid=str(ds.SOPInstanceUID);assert uid in expected
 assert uid not in received, 'duplicate imported SOP Instance UID'
 item=expected[uid];assert np.all(ds.pixel_array==item['number']),f
 frames=int(getattr(ds,'NumberOfFrames',1));assert frames==item['frames']
 received[uid]=frames
assert len(received)==count, 'received SOPs must be persisted in DATABASE.noindex, not quarantined'
assert 'not merged into the incoming index' not in log
sql = next((a.run/'db').rglob('Database.sql'))
with sqlite3.connect(sql.resolve().as_uri()+'?mode=ro', uri=True) as database:
 assert database.execute('SELECT COUNT(*) FROM ZIMAGE').fetchone()[0] == sum(received.values()), 'database frame inventory differs'

get_models={'1.2.840.10008.5.1.4.1.2.1.3','1.2.840.10008.5.1.4.1.2.2.3'}
find_models={'1.2.840.10008.5.1.4.1.2.1.1','1.2.840.10008.5.1.4.1.2.2.1'}
gets=[x for x in peer['associations'] if any(c['abstractSyntax'] in get_models for c in x['contexts'])]
finds=[x for x in peer['associations'] if any(c['abstractSyntax'] in find_models for c in x['contexts'])]
assert len(gets)==1, 'one association must carry all C-GET stores'
assert len(finds)==sum(x['event']=='C_FIND_RQ' for x in peer['timeline'])
assert len(peer['associations'])==len(gets)+len(finds), 'unexpected storage/reconnect association'
contexts=gets[0]['contexts']
for sop in {x['sopClass'] for x in expected.values()}:
 assert any(c['abstractSyntax']==sop and c['proposedSCP'] is True for c in contexts),sop
timeline=peer['timeline'];assert sum(x['event']=='C_GET_RQ' for x in timeline)==1
assert sum(x['event']=='C_STORE_RSP' and int(x['Status'])==0 for x in timeline)==count
terminals=[x for x in timeline if x['event']=='C_GET_RSP' and int(x['Status'])!=0xff00]
assert len(terminals)==1, 'one final C-GET response is required'
terminal=terminals[0]
cancel_seconds=None
if a.mode=='complete':
 assert received.keys()==expected.keys() and count==6 and sum(received.values())==13
 assert int(end[3])==6 and int(terminal['Status'])==0
elif a.mode=='failure':
 assert count==2 and 'C-GET incomplete:' in log and 'CGET_NOTICE main=1' in log
 assert int(terminal['Status'])==0xc000
 # The synthetic peer's contradictory remaining+failed counters are tracked in #202.
else:
 assert (count==0 if a.mode=='cancel-before-first' else 0<count<6) and int(end[4])==1 and 'C-GET cancelled:' in log and 'CGET_NOTICE main=1' in log
 assert any(x['event']=='C_CANCEL_RQ' for x in timeline) and int(terminal['Status'])==0xfe00
 cancel_seconds=float(end[1])-float(re.search(r'CGET_INDEPENDENT_CANCEL ([\d.]+)',log)[1]);assert 0<=cancel_seconds<7
print(json.dumps({'objects':count,'frames':sum(received.values()),'listener':False,'associationCount':len(peer['associations']),'pixelsChecked':True,'databaseFramesChecked':True,'mode':a.mode,'cancelSeconds':round(cancel_seconds,3) if cancel_seconds else None},indent=2))
