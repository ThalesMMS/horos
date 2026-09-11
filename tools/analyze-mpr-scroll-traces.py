#!/usr/bin/env python3
"""Analyze preserved, individual xctrace XML tables; never use UI RPC time as latency."""
import argparse
from bisect import bisect_left
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

ROOT = None
EVENT_SYMBOL = 'MPRDCMView scrollWheel:'


def table(name, schema):
    root = ET.parse(ROOT / f'{name}-{schema}.xml').getroot()
    ids = {e.get('id'): e for e in root.iter() if e.get('id')}

    def resolve(e):
        while e.get('ref'):
            e = ids[e.get('ref')]
        return e

    return root.findall('.//row'), resolve


def stats(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    return dict(count=len(values), median_ms=statistics.median(values),
                p95_ms=values[math.ceil(.95 * len(values)) - 1],
                min_ms=values[0], max_ms=values[-1], sum_ms=sum(values),
                over_33_ms=sum(v > 33 for v in values))


def analyze(run):
    name = run['name']
    toc = ET.parse(ROOT / f'{name}-toc.xml')
    zero = datetime.fromisoformat(toc.findtext('.//summary/start-date')).timestamp()
    duration = float(toc.findtext('.//summary/duration'))
    start = run['start_unix_ms'] / 1000 - zero
    end = run['end_unix_ms'] / 1000 - zero
    if not 0 < start < end + .6 < duration:
        raise ValueError(f'{name}: recording does not cover the complete input and post-input window')

    rows, resolve = table(name, 'time-profile')
    scroll_samples = []
    inclusive = Counter()
    main_inclusive = Counter()
    main_leaf = Counter()
    cpu = main_cpu = 0
    for row in rows:
        timestamp = int(resolve(row[0]).text) / 1e9
        if not start - .1 <= timestamp <= end + .6:
            continue
        weight_ms = int(resolve(row[5]).text) / 1e6
        names = [resolve(f).get('name', '') for f in resolve(row[6]).findall('frame')]
        cpu += weight_ms
        for symbol in set(names):
            inclusive[symbol] += weight_ms
        if 'Main Thread' in resolve(row[1]).get('fmt', ''):
            main_cpu += weight_ms
            for symbol in set(names):
                main_inclusive[symbol] += weight_ms
            if names:
                main_leaf[names[0]] += weight_ms
        if any(EVENT_SYMBOL in symbol for symbol in names):
            scroll_samples.append(timestamp)
    scroll_samples.sort()

    rows, resolve = table(name, 'potential-hangs')
    related, all_during, after = [], [], []
    for row in rows:
        timestamp = int(resolve(row[0]).text) / 1e9
        milliseconds = int(resolve(row[1]).text) / 1e6
        interval = dict(start_seconds=timestamp, duration_ms=milliseconds)
        if start - .1 <= timestamp <= end + .05:
            all_during.append(interval)
            index = bisect_left(scroll_samples, timestamp)
            if index < len(scroll_samples) and scroll_samples[index] <= timestamp + milliseconds / 1000:
                related.append(interval)
        elif end + .05 < timestamp <= end + .6:
            after.append(interval)
    if not scroll_samples:
        raise ValueError(f'{name}: no sampled native input handler in the input window')

    rows, resolve = table(name, 'device-thermal-state-intervals')
    thermal = [[resolve(c).get('fmt', resolve(c).text) for c in row] for row in rows]
    result = dict(**run, fully_covered=True, trace_duration_seconds=duration,
                  sampled_event_samples=len(scroll_samples),
                  input_interval_seconds=[start, end], cpu_window_seconds=[start - .1, end + .6],
                  scroll_associated_intervals=related,
                  scroll_pause_stats=stats([v['duration_ms'] for v in related]),
                  all_during_stats=stats([v['duration_ms'] for v in all_during]),
                  post_input_intervals=after, weighted_cpu_ms=cpu, weighted_main_cpu_ms=main_cpu,
                  cpu_ms_per_action=cpu / run['actions'], thermal=thermal,
                  cpu_inclusive_ms=inclusive.most_common(),
                  main_cpu_inclusive_ms=main_inclusive.most_common(),
                  main_cpu_leaf_ms=main_leaf.most_common())
    (ROOT / f'{name}-analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    global ROOT, EVENT_SYMBOL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path,
                        help='matched-runs.json and individual xctrace XML tables')
    parser.add_argument('--event-symbol', default=EVENT_SYMBOL,
                        help='native event handler, for example VRView mouseDragged:')
    args = parser.parse_args()
    ROOT = args.directory
    EVENT_SYMBOL = args.event_symbol
    runs = [analyze(run) for run in json.loads((ROOT / 'matched-runs.json').read_text())]
    apps = {}
    for app in dict.fromkeys(run['app'] for run in runs):
        selected = [run for run in runs if run['app'] == app]
        values = [v['duration_ms'] for run in selected for v in run['scroll_associated_intervals']]
        actions = sum(run['actions'] for run in selected)
        cpu = sum(run['weighted_cpu_ms'] for run in selected)
        apps[app] = dict(actions=actions, pause_stats=stats(values), weighted_cpu_ms=cpu,
                         cpu_ms_per_action=cpu / actions,
                         per_run=[dict(name=run['name'], pauses=run['scroll_pause_stats'],
                                       cpu_ms_per_action=run['cpu_ms_per_action'],
                                       thermal=run['thermal']) for run in selected])
    result = dict(apps=apps,
                  metric='Hangs intervals containing a sampled native ' + EVENT_SYMBOL + ' call; not input-to-display latency or FPS',
                  sampling='Time Profiler 1 ms; Hangs reporting threshold 1 ms; nearest-rank p95',
                  cpu='Sum of Time Profiler sample weights in input window plus 100 ms before and 600 ms after; normalized by action count')
    (ROOT / 'matched-comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
