#!/usr/bin/env python3
"""Validate native sharing preference toggles, endpoint and main-thread progress."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('run',type=Path)
p.add_argument('--restart',action='store_true')
a=p.parse_args()
report=json.loads((a.run/'results.json').read_text())
rows={r['case']:r for r in report['cases']}
assert set(rows)=={'initial-off','occupied-on','occupied-off','free-on','publish-error-off','recover-on','final-off'}
for name,row in rows.items():
 assert 0<=row['seconds']<1,(name,row)
 if name in ('free-on','recover-on'):
  assert row['preference'] and row['listenerPort']==row['advertisedPort']==11284,row
 elif name=='occupied-on':assert row['preference'] and row['listenerPort']==0,row
 else:assert not row['preference'] and row['listenerPort']==row['advertisedPort']==0,row
assert 0<report['maxHeartbeatGap']<.25,report
assert report['publicationFailureInjected'] is True
if a.restart:assert report['startupListenerPort']==11284
print('ok: 7 native toggles, live advertised port, reversible preference; max action %.2f ms, heartbeat %.2f ms%s'%(
 max(r['seconds'] for r in rows.values())*1000,report['maxHeartbeatGap']*1000,', enabled restart' if a.restart else ''))
