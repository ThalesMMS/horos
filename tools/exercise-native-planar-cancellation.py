#!/usr/bin/env python3
"""Open and promptly close only the synthetic S373-LIFETIME-CT-1250 catalog entry.

Uses existing loopback XML-RPC commands. Requires no viewers initially and never
changes images. The companion native plugin must establish whether cancellation
actually interrupted decoding; command acknowledgement alone cannot prove it.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request
import xmlrpc.client

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--port', type=int, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--cycles', type=int, default=3)
a = p.parse_args()
if not 1 <= a.port <= 65535 or not 1 <= a.cycles <= 10:
    p.error('valid port and 1..10 cycles required')
if a.output.exists():
    p.error('output already exists')


def call(method, parameters):
    request = urllib.request.Request(f'http://127.0.0.1:{a.port}/',
        data=xmlrpc.client.dumps((parameters,),methodname=method).encode(),
        headers={'Content-Type':'text/xml'})
    with urllib.request.urlopen(request, timeout=30) as response:
        answer = xmlrpc.client.loads(response.read())[0][0]
    if str(answer.get('error')) != '0':
        raise RuntimeError(f'{method}: {answer.get("error")}')
    return answer


uid = '2.25.166623716792404446536027970935595543351'
rows = call('DBWindowFind', {'table':'Series','execute':'Nothing',
    'request':"study.patientID == 'LOCAL-SCROLL-CT' AND name == 'S373-LIFETIME-CT-1250'"})['elements']
if len(rows) != 1 or rows[0].get('seriesDICOMUID') != uid or int(rows[0].get('numberOfImages',0)) != 1250:
    p.error('the exact synthetic series is not present in this catalog')
if call('GetDisplayed2DViewerSeries', {})['elements']:
    p.error('close existing test viewers before this sequence')
records = []
for cycle in range(a.cycles):
    started = time.monotonic()
    call('DisplaySeries', {'SeriesInstanceUID':uid})
    deadline = time.monotonic()+20
    while True:
        rows = call('GetDisplayed2DViewerSeries', {})['elements']
        if any(row.get('seriesDICOMUID') == uid for row in rows):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('requested viewer was not observed; inspect the native UI')
        time.sleep(.01)
    observed = time.monotonic()
    call('Close2DViewerWithSeriesUID', {'uid':uid})
    remaining = call('GetDisplayed2DViewerSeries', {})['elements']
    if remaining:
        raise RuntimeError('a viewer remains after closing the synthetic series')
    records.append({'cycle':cycle+1, 'observedAfterSeconds':observed-started,
                    'closeCallSeconds':time.monotonic()-observed, 'viewersAfter':len(remaining)})
    time.sleep(.3)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(records,indent=2)+'\n')
print(f'{a.cycles} open/close cycles; inspect the native worker record before claiming cancellation')
