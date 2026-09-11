#!/usr/bin/env python3
"""Check native autorouting at four SCPs, including repeated rule application."""
import argparse,json
from collections import Counter
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('fixture',type=Path);p.add_argument('run',type=Path);p.add_argument('--baseline',action='store_true');p.add_argument('--limit',type=int,default=3);p.add_argument('--current-repetitions',type=int,default=2);a=p.parse_args()
m=json.loads((a.fixture/'manifest.json').read_text())
expected=[['modality','description','matching'],['description','matching'],['modality','matching'],['matching']]
if a.baseline:expected=[[],[],[],[]]
summary=[]
for i,names in enumerate(expected):
 state=json.loads((a.run/f'peer{i}/store-results.json').read_text())
 want=Counter({uid:a.current_repetitions for uid in m['current']})
 for name in names[:a.limit]:want.update(m[name])
 got=Counter(x['sop_instance'] for x in state['stored'])
 assert got==want,(i,got,want)
 assert not state['refused'] and len(state['associations'])==a.current_repetitions
 assert all(x['status']=='0x0000' for x in state['stored'])
 summary.append({'destination':i,'received':sum(got.values()),'priorStudies':names[:a.limit],'currentRepetitions':a.current_repetitions})
print(json.dumps(summary,indent=2))
