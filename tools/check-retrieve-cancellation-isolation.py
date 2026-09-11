#!/usr/bin/env python3
"""Check native batch cancellation against per-instance peer records and pixels."""
import argparse,json,re
from pathlib import Path
import numpy as np
import pydicom
p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--global-abort',action='store_true');a=p.parse_args()
assert 'local-validation' in a.run.resolve().parts
logs=[(a.run/f'app{i}/horos.log').read_text(errors='replace') for i in range(2)]
assert all('ISOLATION_EXCEPTION' not in s and 'ISOLATION_NO_STUDY' not in s for s in logs)
log='\n'.join(logs)
ends={int(i):(float(t),int(n),int(total),int(cancelled)) for i,t,n,total,cancelled in re.findall(r'ISOLATION_END operation(\d) ([\d.]+) received=(\d+) expected=(\d+) cancelled=(\d)',log)}
assert set(ends)=={0,1,2},ends
assert len(re.findall('ISOLATION_WATCHDOG running=0',log))==3 and 'ISOLATION_WATCHDOG running=1' not in log
cancel=float(re.search(r'ISOLATION_CANCEL ([\d.]+)',log)[1]);result={}
for i in range(3):
 state=json.loads((a.run/f'peer{i}-results.json').read_text())
 source=a.run.parent/f'peer{i}/fixture'
 expected={str(pydicom.dcmread(f,stop_before_pixels=True).SOPInstanceUID) for f in source.glob('*.dcm')}
 assert len(expected)==30
 db=a.run/f'app{0 if i<2 else 1}/db';received=set()
 for f in db.rglob('*.dcm'):
  ds=pydicom.dcmread(f)
  if str(ds.SOPInstanceUID) not in expected:continue
  pixels=((int(ds.SeriesNumber)*1000+int(ds.InstanceNumber)+np.arange(256))%4096).reshape(16,16)
  assert np.array_equal(ds.pixel_array,pixels),f
  received.add(str(ds.SOPInstanceUID))
 end,count,total,thread_cancelled=ends[i];assert total==30 and len(received)==count,(i,len(received),count)
 stopped=a.global_abort or i==0
 if stopped:
  assert 0<count<30 and 0<=end-cancel<2,(i,ends[i],cancel)
  assert max(r['time'] for r in state['httpStarted'])<=cancel+1,(i,state['httpStarted'])
 else:
  assert count==30 and received==expected and end>cancel
  assert {r['objectUID'] for r in state['wado']}==expected
 assert thread_cancelled==int(i==0 and not a.global_abort)
 result[str(i)]={'receivedObjects':count,'expectedObjects':total,'stoppedAfterCancelSeconds':round(end-cancel,3) if stopped else None,'pixelsChecked':True}
assert not (a.run/'control/horos-dicom-control/abort').exists()
print(json.dumps(result,indent=2))
