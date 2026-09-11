#!/usr/bin/env python3
"""Read native PlanarPerformance signposts exported by xctrace.

Pairs the raw Begin/End records and requires every requested scroll event.
Reports handler, preparation, image drawing, overlays/flush and event-to-flush
separately. A processed input without its own submitted index is coalesced;
it is not silently counted as an independently displayed frame. flushBuffer
return is not a compositor presentation timestamp. No UI driving occurs here.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import xml.etree.ElementTree as ET


def read_records(path):
    root = ET.parse(path).getroot()
    definitions = {e.get('id'): e for e in root.iter() if e.get('id') is not None}

    def value(element):
        if element.get('ref') is not None:
            return value(definitions[element.get('ref')])
        return (element.text or '') + ''.join(value(child) for child in element)

    columns = [c.findtext('mnemonic') for c in root.find('.//schema')]
    records = []
    for row in root.iter('row'):
        data = dict(zip(columns, map(value, row), strict=True))
        if data['category'] != 'PlanarPerformance':
            continue
        fields = {key: float(number) if '.' in number else int(number) for key, number in
                  re.findall(r'(\w+)=\s*(-?\d+(?:\.\d+)?)', data['message'])}
        assert fields and all(math.isfinite(v) for v in fields.values())
        records.append({'time': int(data['time']), 'id': int(data['identifier']),
                        'name': data['name'], 'type': data['event-type'], **fields})
    assert records, 'No PlanarPerformance records; enable the development trace and record os_signpost'
    return records


def summarize(values):
    values = sorted(values)
    if not values:
        return None
    position = (len(values)-1)*0.95
    lo = int(position)
    p95 = values[lo] if lo+1 == len(values) else values[lo]+(values[lo+1]-values[lo])*(position-lo)
    return {'n': len(values), 'median': statistics.median(values), 'p95': p95,
            'min': values[0], 'max': values[-1]}


def verify(path, expected_events, backend, selection=None):
    records = read_records(path)
    inputs, draws = {}, {}
    for record in records:
        name, kind = record['name'], record['type']
        destination = inputs if name == 'PlanarScroll' else draws
        key = kind if name in ('PlanarScroll', 'PlanarDraw') else name
        group = destination.setdefault(record['id'], {})
        assert key not in group, f'Duplicate signpost {record["id"]}/{key}'
        group[key] = record
    assert len(inputs) == expected_events, f'Expected {expected_events} scroll events, captured {len(inputs)}'
    assert all(set(event) == {'Begin','End'} for event in inputs.values()), 'Incomplete scroll interval'
    if selection is not None:
        offset, count = selection
        assert offset >= 0 and count > 0 and offset + count <= len(inputs), 'Invalid input selection'
        ordered_ids = sorted(inputs, key=lambda key: inputs[key]['Begin']['time'])
        inputs = {key: inputs[key] for key in ordered_ids[offset:offset+count]}
    complete_draws = [draw for draw in draws.values()
                      if set(draw) == {'Begin','End','PlanarPrepared','PlanarImageDrawn'}]
    complete_draws.sort(key=lambda d: d['Begin']['time'])
    assert complete_draws, 'No complete draw spans'
    samples, coalesced, unchanged = [], [], []
    ms = lambda end, start: (end['time']-start['time'])/1_000_000
    ordered = sorted(inputs.values(), key=lambda i: i['Begin']['time'])
    for event in ordered:
        start, end = event['Begin'], event['End']
        assert start['view'] == end['view'] and ms(end,start) >= 0
        if start['from'] == end['to']:
            unchanged.append(int(start['id']))
            continue
        assert all('input' in d['Begin'] for d in complete_draws), 'Draw spans need explicit input identities'
        following = next((d for d in complete_draws if d['Begin']['view'] == start['view']
                          and d['Begin']['input'] == start['id'] and d['Begin']['index'] == end['to']), None)
        if following is None:
            later = next((i for i in ordered if i['Begin']['view'] == start['view']
                          and i['Begin']['time'] > start['time']), None)
            assert later is not None, 'Capture ended before the last changed input was drawn'
            coalesced.append({'input': int(start['id']), 'requested_index': int(end['to']),
                              'superseded_by_input': int(later['Begin']['id'])})
            continue
        drawn, flushed = following['Begin'], following['End']
        prepared, image = following['PlanarPrepared'], following['PlanarImageDrawn']
        assert drawn['index'] == flushed['index'], 'Image changed while a draw was in progress'
        assert drawn['view'] == prepared['view'] == image['view'] == flushed['view']
        assert drawn['time'] <= prepared['time'] <= image['time'] <= flushed['time']
        assert int(prepared['metal']) == (backend == 'metal'), 'Unexpected renderer/fallback in measured draw'
        assert drawn['time'] >= start['time']
        assert flushed['cpu_s'] >= 0 and flushed['footprint_bytes'] > 0, 'Process counters unavailable'
        age = start['age_ms']
        sample = {'input': int(start['id']), 'draw': int(drawn['id']), 'view': int(start['view']),
                  'from': int(start['from']), 'to': int(end['to']),
                  'precise': bool(start['precise']), 'inverted': bool(start['inverted']),
                  'handler_ms': ms(end,start), 'prepare_ms': ms(prepared,drawn),
                  'image_ms': ms(image,prepared), 'overlays_and_flush_ms': ms(flushed,image),
                  'draw_ms': ms(flushed,drawn), 'handler_to_flush_ms': ms(flushed,start),
                  'event_age_ms': age if age >= 0 else None,
                  'event_to_flush_ms': ms(flushed,start)+age if age >= 0 else None,
                  'gpu_ms': prepared['gpu_ms'] if prepared['gpu_ms'] >= 0 else None,
                  'legacy_upload': bool(prepared['legacy_upload']),
                  'process_cpu_s': flushed['cpu_s'], 'footprint_bytes': int(flushed['footprint_bytes']),
                  'flush_time_ns': flushed['time']}
        samples.append(sample)
    assert samples, 'No changed input with a matching submitted frame'
    assert len({s['draw'] for s in samples}) == len(samples), 'Multiple inputs matched one submitted frame'
    for draw in draws.values():
        if set(draw) != {'Begin','End','PlanarPrepared','PlanarImageDrawn'}:
            assert not any(ordered[0]['Begin']['time'] <= row['time'] <= samples[-1]['flush_time_ns']
                           for row in draw.values()), 'Incomplete draw span inside the measured sequence'
    result = {'schema': 1, 'backend': backend, 'signposts_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'scroll_events': len(inputs), 'changed_with_own_draw': len(samples),
              'coalesced': coalesced, 'unchanged': unchanged,
              'incomplete_other_draws': len(draws)-len(complete_draws),
              'endpoint': 'flushBuffer_return_not_compositor', 'samples': samples}
    if selection is not None:
        result.update(capture_scroll_events=expected_events, input_selection=list(selection))
    metrics = ['handler_ms','prepare_ms','image_ms','overlays_and_flush_ms','draw_ms',
               'handler_to_flush_ms','event_age_ms','event_to_flush_ms','gpu_ms','footprint_bytes']
    result['summary'] = {key: summarize(s[key] for s in samples if s[key] is not None) for key in metrics}
    result['process_cpu_delta_s'] = samples[-1]['process_cpu_s']-samples[0]['process_cpu_s']
    result['sampled_span_s'] = (samples[-1]['flush_time_ns']-samples[0]['flush_time_ns'])/1_000_000_000
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('signposts', type=Path)
    parser.add_argument('--expected-events', type=int, required=True)
    parser.add_argument('--backend', choices=['gl','metal'], required=True)
    parser.add_argument('--select-inputs', nargs=2, type=int, metavar=('OFFSET','COUNT'),
                        help='measure a contiguous input subset after checking the complete capture count')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.expected_events > 0
    report = verify(args.signposts, args.expected_events, args.backend, args.select_inputs)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report[key] for key in ('scroll_events','changed_with_own_draw','coalesced',
                                                'unchanged','summary')}, indent=2))
