#!/usr/bin/env python3
"""Check an application-produced UID manifest and the native query-column value."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('snapshot',type=Path);p.add_argument('--imported',type=int,required=True);p.add_argument('--expected',type=int,required=True);p.add_argument('--duplicates',type=int,default=0);p.add_argument('--rejected',type=int,default=0);p.add_argument('--unexpected',type=int,default=0);p.add_argument('--unknown',action='store_true');a=p.parse_args()
values=json.loads(a.snapshot.read_text());assert len(values)==1;v=values[0]
assert v['inventoryConfirmed']==(not a.unknown) and v['expectedCount']==a.expected
assert v['importedCount']==a.imported
assert len(v['duplicateUIDs'])==a.duplicates and len(v['rejectedUIDs'])==a.rejected and len(v['unexpectedUIDs'])==a.unexpected
if a.unknown:
 assert not v['isComplete'] and v['indicator'].startswith('?')
else:
 assert len(v['missingUIDs'])==a.expected-a.imported
 assert v['isComplete']==(a.expected>0 and a.imported==a.expected)
 assert v['indicator']==f'{round(100*a.imported/a.expected)}% ({a.imported}/{a.expected})'
assert v['summary'] in v['indicatorExplanation']
print(json.dumps({'indicator':v['indicator'],'complete':v['isComplete'],'missing':len(v['missingUIDs']),'duplicates':a.duplicates,'rejections':a.rejected,'unexpected':a.unexpected},indent=2))
