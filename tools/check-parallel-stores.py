#!/usr/bin/env python3
"""Verify concurrent native sends from receiver syntax/pixels and report paths."""
import argparse,json,re,hashlib
from pathlib import Path
import numpy as np,pydicom
p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('peer0',type=Path);p.add_argument('peer1',type=Path);p.add_argument('--one-rejection',action='store_true');a=p.parse_args()
assert 'local-validation' in a.run.resolve().parts
log=(a.run/'horos.log').read_text(errors='replace');inputs=json.loads((a.run/'inputs.json').read_text());reports=json.loads((a.run/'report-paths.json').read_text());temporary=json.loads((a.run/'temporary-directories.json').read_text())
assert log.count('PARALLEL_STORE_WATCHDOG running=0')==2 and 'PARALLEL_STORE_WATCHDOG running=1' not in log
assert len(temporary)==2 and len(set(temporary.values()))==2
assert all(not Path(d).exists() for d in temporary.values())
starts={int(i):float(t) for i,t in re.findall(r'PARALLEL_STORE_START (\d) ([\d.]+)',log)}
ends={int(i):(float(t),int(sent),int(failed)) for i,t,sent,failed in re.findall(r'PARALLEL_STORE_END (\d) ([\d.]+) sent=(\d+) failed=(\d+)',log)}
assert set(starts)==set(ends)=={0,1} and max(starts.values())<min(v[0] for v in ends.values()),'sends did not overlap'
result={};windows=[]
for i,peer in enumerate((a.peer0,a.peer1)):
 state=json.loads((peer/'store-results.json').read_text());rejected=1 if i==1 and a.one_rejection else 0
 assert len(state['associations'])==1
 assert state['associations'][0]['calling_aetitle']==('SEND_B' if i else 'SEND_A')
 assert len(state['stored'])==20-rejected and len(state['refused'])==rejected
 assert ends[i][1:]==(20-rejected,rejected),ends
 assert len(reports[str(i)])==20 and set(reports[str(i)])==set(inputs[i]),'report contains another send or temporary paths'
 source={}
 for path in inputs[i]:
  ds=pydicom.dcmread(path);source[str(ds.SOPInstanceUID)]=ds
 received={x['sop_instance'] for x in state['stored']};refused={x['sop_instance'] for x in state['refused']}
 assert received|refused==source.keys() and not received&refused
 syntax='1.2.840.10008.1.2.4.70' if i else '1.2.840.10008.1.2.1'
 for record in state['stored']:
  assert record['transfer_syntax']==syntax
  ds=pydicom.dcmread(peer/'received'/(record['sop_instance']+'.dcm'))
  assert str(ds.file_meta.TransferSyntaxUID)==syntax
  assert np.array_equal(ds.pixel_array,source[str(ds.SOPInstanceUID)].pixel_array)
 windows.append((min(x['received_at'] for x in state['stored']),max(x['received_at'] for x in state['stored'])))
 result[str(i)]={'stored':len(received),'refused':len(refused),'reportEntries':20,'transferSyntax':syntax,'pixelsChecked':True}
assert max(w[0] for w in windows)<min(w[1] for w in windows),'receivers did not observe overlapping transfers'
hashes=a.run/'source-hashes.json'
if hashes.exists():
 for path,digest in json.loads(hashes.read_text()).items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
print(json.dumps({'sends':result,'distinctTemporaryDirectoriesRemoved':True,'receiverOverlapSeconds':round(min(w[1] for w in windows)-max(w[0] for w in windows),3)},indent=2))
