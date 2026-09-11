#!/usr/bin/env python3
"""Summarize only process-memory rows from an xctrace Activity Monitor table export."""
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def summarize(path):
    root = ET.parse(path).getroot()
    schema = root.find('.//schema')
    assert schema is not None and schema.get('name') == 'activity-monitor-process-live'
    columns = [col.findtext('mnemonic') for col in schema.findall('col')]
    references = {node.get('id'): node for node in root.iter() if node.get('id')}
    def value(node):
        if node.get('ref'):
            node = references[node.get('ref')]
        return node.text
    rows = list(root.iter('row'))
    assert rows, 'No process samples'
    samples = [(int(value(row[columns.index('start')])),
                int(value(row[columns.index('memory-physical-footprint')]))) for row in rows]
    print(json.dumps(dict(samples=len(samples), first_seconds=samples[0][0]/1e9,
        last_seconds=samples[-1][0]/1e9, first_bytes=samples[0][1], last_bytes=samples[-1][1],
        minimum_bytes=min(m for _, m in samples), maximum_bytes=max(m for _, m in samples)), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('table_xml', type=Path)
    summarize(parser.parse_args().table_xml)
