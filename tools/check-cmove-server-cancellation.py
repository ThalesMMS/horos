#!/usr/bin/env python3
"""Validate a native server's C-MOVE cancellation, counters, release and pixels."""
import argparse
import json
import sqlite3
from pathlib import Path
import numpy
import pydicom
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('fixture',type=Path)
p.add_argument('output',type=Path)
p.add_argument('--complete',action='store_true')
p.add_argument('--database',type=Path,help='private database whose current cancellation log must be verified')
a=p.parse_args();fixture=json.loads(a.fixture.read_text());r=json.loads((a.output/'result.json').read_text())
expected={x['sopInstance']:x for x in fixture['instances']}
received=r['received'];timeline=r['timeline'];final=r['responses'][-1]
assert final['Status']==(0 if a.complete else 0xFE00),final
count=len(expected) if a.complete else 1
assert len(received)==len(set(received))==count,received
assert final['NumberOfCompletedSuboperations']==count,final
assert final.get('NumberOfFailedSuboperations',0)==0 and final.get('NumberOfWarningSuboperations',0)==0,final
assert final.get('NumberOfRemainingSuboperations',0)==len(expected)-count,final
if not a.complete:
    cancel=next(x['time'] for x in timeline if x['event']=='cancel-sent')
    assert not [x for x in timeline if x['event']=='store-start' and x['time']>cancel],timeline
    assert len([x for x in timeline if x['event']=='cancel-sent'])==1
releases=[x['time'] for x in timeline if x['event']=='store-association-released']
final_time=[x['time'] for x in timeline if x['event']=='move-response'][-1]
assert releases and releases[-1]<=final_time,timeline
assert any(x['event']=='move-association-released' and x['released'] for x in timeline)
frames=0
for uid in received:
    ds=pydicom.dcmread(a.output/(uid+'.dcm'));entry=expected[uid]
    assert str(ds.SOPInstanceUID)==uid
    assert numpy.all(ds.pixel_array==entry['number'])
    frames+=int(getattr(ds,'NumberOfFrames',1))
if a.complete:assert frames==fixture['totalFrames']
print(f'PASS: {count} objects/{frames} frames, exact counters, storage and move associations released')

if a.database:
    with sqlite3.connect(a.database) as db:
        row=db.execute("select ZMESSAGE,ZNUMBERIMAGES,ZNUMBERSENT,ZENDTIME from ZLOGENTRY where ZSTARTTIME >= ? and ZMESSAGE='Cancelled' order by Z_PK desc limit 1", (r['startedAt']-978307200,)).fetchone()
    assert row and row[:3]==('Cancelled',len(expected),1) and row[3] is not None,row
    print('PASS: current transfer log records cancellation and 1 of 6 sent')
