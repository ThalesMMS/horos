#!/usr/bin/env python3
"""Measure an existing Horos series through XML-RPC and its native loading log.

Run a fresh isolated application for each sample, with stdout/stderr redirected
to --log. Import synthetic data before measuring. The native duration covers
ViewerController.loadImageData; neither the RPC ACK nor the log is a compositor
presentation timestamp. Keep logs and results outside version control.
"""
import argparse
import json
from pathlib import Path
import re
import time
import urllib.request
import xmlrpc.client

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--series', required=True)
parser.add_argument('--expected-slices', type=int, required=True)
parser.add_argument('--log', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    parser.error('Preserve the existing result and choose another output')


def call(method, parameters):
    request = urllib.request.Request(f'http://127.0.0.1:{args.port}/',
        data=xmlrpc.client.dumps((parameters,), methodname=method).encode(),
        headers={'Content-Type': 'text/xml'})
    with urllib.request.urlopen(request, timeout=30) as response:
        values, _ = xmlrpc.client.loads(response.read())
    result = values[0]
    if str(result.get('error')) != '0':
        raise RuntimeError(f'{method}: {result}')
    return result


if call('GetDisplayed2DViewerSeries', {})['elements']:
    raise SystemExit('Start with all viewers closed; do not time an already loaded series')
offset = args.log.stat().st_size
started = time.monotonic()
call('DisplaySeries', {'SeriesInstanceUID': args.series})
ack_seconds = time.monotonic() - started
deadline = started + 60
while time.monotonic() < deadline:
    with args.log.open('rb') as stream:
        stream.seek(offset)
        text = stream.read().decode('utf-8', errors='replace')
    durations = re.findall(r'end loading: ([0-9.]+) \[s\]', text)
    if durations:
        if len(durations) != 1 or text.count('start loading') != 1:
            raise SystemExit('Ambiguous native loading spans; use one viewer per sample')
        observed_seconds = time.monotonic() - started
        break
    time.sleep(0.02)
else:
    raise SystemExit('No completed native load within 60 seconds; inspect the application')
displayed = call('GetDisplayed2DViewerSeries', {})['elements']
if len(displayed) != 1 or displayed[0].get('seriesDICOMUID') != args.series:
    raise SystemExit('The requested series is not the only displayed viewer')
if int(displayed[0]['numberOfImages']) != args.expected_slices:
    raise SystemExit('The displayed series has an unexpected slice count')
result = dict(native_load_seconds=float(durations[0]), rpc_ack_seconds=ack_seconds,
    request_to_observed_load_log_seconds=observed_seconds,
    slices=args.expected_slices, series_observed=True,
    scope='loadImageData; not compositor presentation or total application startup')
args.output.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
