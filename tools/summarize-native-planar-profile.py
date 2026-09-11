#!/usr/bin/env python3
"""Summarize exported Time Profiler samples inside native scroll intervals.

Pass time-profile XML and the GL/Metal reports from verify-native-planar-scroll.
Weights describe sampled CPU time, not wall time, GPU time or a causal verdict.
No private paths, addresses or thread IDs are copied into the summary.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def summarize(profile, reports):
    root = ET.parse(profile).getroot()
    definitions = {e.get('id'): e for e in root.iter() if e.get('id') is not None}

    def resolve(element):
        while element.get('ref') is not None:
            element = definitions[element.get('ref')]
        return element

    def frames(element):
        element = resolve(element)
        if element.tag == 'frame':
            return [element.get('name', '<unnamed>')]
        return [name for child in element for name in frames(child)]

    columns = [c.findtext('mnemonic') for c in root.find('.//schema')]
    output = {}
    for backend, report in reports.items():
        samples = report['samples']
        start = samples[0]['flush_time_ns'] - samples[0]['handler_to_flush_ms'] * 1e6
        end = samples[-1]['flush_time_ns']
        leaf, inclusive = Counter(), Counter()
        count = total = missing = 0
        for row in root.iter('row'):
            data = dict(zip(columns, row, strict=True))
            if not start <= int(resolve(data['time']).text) <= end:
                continue
            weight = int(resolve(data['weight']).text)
            names = frames(data['stack'])
            total += weight
            count += 1
            if not names:
                missing += weight
                names = ['<stack unavailable>']
            leaf[names[0]] += weight
            inclusive.update({name: weight for name in set(names)})
        assert count, 'No CPU samples in the input interval'
        top = lambda counter: [{'symbol': name, 'sampledMS': ns / 1e6,
                                'sampledPercent': 100 * ns / total}
                               for name, ns in counter.most_common(15)]
        output[backend] = {'samples': count, 'sampledMS': total / 1e6,
                           'unavailableStackMS': missing / 1e6,
                           'leaf': top(leaf), 'inclusive': top(inclusive)}
    return {'profileSHA256': hashlib.sha256(profile.read_bytes()).hexdigest(),
            'scope': 'sampled CPU stacks inside each scroll interval; not a causal or leak diagnosis',
            'backends': output}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    parser.add_argument('reports', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.profile, json.loads(args.reports.read_text()))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS:', {b: r['samples'] for b, r in result['backends'].items()}, 'CPU samples')
