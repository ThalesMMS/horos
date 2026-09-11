#!/usr/bin/env python3
"""Verify the local PluginFilter/native loading record for #373.

This checks completion, identity and quantitative pixels, not elapsed-time speed.
The observer fixture adds overhead and does not measure compositor presentation.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

SERIES = {
    'S373-LIFETIME-CT-1250': ('2.25.166623716792404446536027970935595543351', 1250),
    'S373-LIFETIME-MR-500': ('2.25.232693044716974896539379152923732644845', 500),
}


def verify(rows, displayed_after_close):
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    require(rows and rows[0]['event'] == 'plugin-loaded', 'missing native plugin load')
    require(rows[0]['api'] == 'PluginFilter', 'fixture did not use the PluginFilter base class')
    require(str(displayed_after_close.get('error')) == '0'
            and displayed_after_close.get('elements') == [], 'test viewers remain open')
    events = defaultdict(list)
    for row in rows:
        events[row['event']].append(row)
        worker = row['event'] in ('worker-started', 'worker-ended')
        require(row['mainThread'] is (not worker), 'UI or worker event on the wrong thread')
    require(len(events['plugin-loaded']) == 1, 'multiple native runs mixed together')
    require(events['input'], 'no input reached the plugin facade')

    # Keep occurrences rather than treating an allocator address as permanent.
    starts, ends, requests, deliveries = (defaultdict(list) for _ in range(4))
    for row in events['worker-started']:
        starts[row['thread']['id']].append(row)
    for row in events['worker-ended']:
        ends[row['thread']['id']].append(row)
    for row in events['request-started']:
        require(row['series'] in SERIES and row['movies'] == 1, 'unexpected native catalog request')
        require(row['slices'] == SERIES[row['series']][1], 'request has the wrong slice count')
        requests[row['thread']['id']].append(row)
    for row in events['delivery-before']:
        deliveries[row['origin']['id']].append(row)
    require(set(starts) == set(ends) == set(requests), 'unpaired worker/request identity')
    cancelled = []
    completed = 0
    for thread, began in starts.items():
        require(thread and len(began) == len(ends[thread]) == len(requests[thread]),
                'missing or duplicated worker boundary')
        for index, begin in enumerate(began):
            end, request = ends[thread][index], requests[thread][index]
            require(begin['uptime'] <= end['uptime'], 'worker ended before it started')
            require(end['total'] == request['slices'] and 0 <= end['loaded'] <= end['total'],
                    'worker decoded the wrong volume extent')
            next_start = began[index+1]['uptime'] if index+1 < len(began) else float('inf')
            callbacks = [d for d in deliveries[thread] if begin['uptime'] <= d['uptime'] < next_start]
            if end['thread']['cancelled']:
                require(not callbacks, 'cancelled worker delivered a completion')
                require(end['loaded'] < end['total'], 'cancellation was only after a fully loaded volume')
                cancelled.append(end['loaded'])
            else:
                require(end['loaded'] == end['total'], 'successful worker left pixels unloaded')
                require(len(callbacks) == 1, 'successful worker did not deliver exactly once')
                require(callbacks[0]['current']['id'] == thread and not callbacks[0]['closing'],
                        'successful completion lost its owner')
                completed += 1
    require(len(cancelled) >= 3 and completed >= 2, 'native cancellation/normal-load matrix incomplete')
    require(len(events['delivery-before']) == len(events['delivery-after']) == completed,
            'native completion span missing')
    for before, after in zip(events['delivery-before'], events['delivery-after']):
        require(before['origin']['id'] == after['origin']['id'], 'completion identity changed')
        require(not after['current']['id'], 'completed worker remained attached')

    loaded_notices = [r for r in events['notification']
                      if r['name'] == 'OsirixViewerControllerDidLoadImagesNotification']
    require(len(loaded_notices) == completed, 'missing or duplicate loaded notification')
    require(all(not r['closing'] and not r['thread']['id'] for r in loaded_notices),
            'notification ran before detaching its load or after close')

    seen, voxels, session_ids = set(), 0, set()
    for row in events['pixel-capture']:
        require(row['series'] in SERIES, 'unexpected pixel fixture')
        uid, count = SERIES[row['series']]
        require(row['seriesUID'] == row['sessionSeriesUID'] == uid, 'session does not use the DICOM SeriesInstanceUID')
        require(row['sameSession'] and row['sessionID'] > 0, 'unstable session identity')
        require(row['voxels'] == count*512*512 and row['mismatches'] == 0 and row['maximumError'] == 0,
                'calibrated native pixels differ from the analytical fixture')
        require(row['metalEnabled'] and not row['fallback'], 'native Metal route not active')
        require(any(s['id'] == row['sessionID'] and s['open'] and not s['stale']
                    and not s['cancelled'] and not s['delivered'] for s in row['sessions']),
                'plugin did not hold a current session and pending token')
        seen.add(row['series']); voxels += row['voxels']; session_ids.add(row['sessionID'])
    require(seen == set(SERIES), 'CT/MR native pixel matrix incomplete')
    require(events['retired-consumers'], 'no consumer teardown observed')
    retired = events['retired-consumers'][-1]
    require(retired['registryCount'] == 0, 'registry retained an open volume')
    require({s['id'] for s in retired['sessions']} == session_ids, 'held plugin session vanished from the audit')
    require(all(not s['open'] and s['cancelled'] and not s['delivered'] for s in retired['sessions']),
            'closed viewer left a live session or deliverable token')
    return {'cancelledWorkers':len(cancelled), 'loadedSlicesAtCancellation':cancelled,
            'completedWorkers':completed, 'nativePixelCaptures':len(events['pixel-capture']),
            'calibratedVoxelChecks':voxels, 'retiredPluginSessions':len(session_ids),
            'inputHookInvocations':len(events['input']), 'registryAfterClose':0,
            'displayedViewersAfterClose':0}


def read_rows(path):
    def nonfinite(value):
        raise ValueError('nonfinite JSON number: '+value)
    return [json.loads(line, parse_constant=nonfinite) for line in Path(path).read_text().splitlines() if line.strip()]


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('events', type=Path)
    p.add_argument('--displayed-after-close', type=Path, required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    result = verify(read_rows(a.events), json.loads(a.displayed_after_close.read_text()))
    rendered = json.dumps(result, indent=2)+'\n'
    if a.output:
        if a.output.exists():
            p.error('output already exists; preserve the old result')
        a.output.write_text(rendered)
    print(rendered, end='')
