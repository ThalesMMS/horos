#!/usr/bin/env python3
"""Reject damaged native lifetime evidence; no private captures ship with Git."""
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--events', type=Path)
p.add_argument('--displayed-after-close', type=Path)
a = p.parse_args()
if not a.events or not a.displayed_after_close:
    p.exit(2, 'needs --events and --displayed-after-close from the native synthetic run\n')
spec = importlib.util.spec_from_file_location('lifetime', root/'tools/verify-native-planar-lifetime.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
original = module.read_rows(a.events)
listing = json.loads(a.displayed_after_close.read_text())
print(json.dumps(module.verify(original, listing), sort_keys=True))


def rejected(name, mutate):
    rows, after = deepcopy(original), deepcopy(listing)
    mutate(rows, after)
    try:
        module.verify(rows, after)
    except (ValueError, KeyError):
        print('PASS: rejects '+name)
        return
    raise AssertionError('accepted damaged evidence: '+name)


def change(event, field, value):
    return lambda rows, _: next(r for r in rows if r['event'] == event).__setitem__(field, value)


rejected('one altered voxel', change('pixel-capture','mismatches',1))
rejected('wrong matrix', change('pixel-capture','voxels',1))
rejected('catalog grouping key as UID', change('pixel-capture','sessionSeriesUID','00000001 1.2.3'))
rejected('Metal disabled', change('pixel-capture','metalEnabled',False))
rejected('unexpected fallback', change('pixel-capture','fallback','paused'))
rejected('UI callback off main', change('notification','mainThread',False))
rejected('lost worker end', lambda rows,_: rows.remove(next(r for r in rows if r['event']=='worker-ended')))
rejected('missing MR pixels', lambda rows,_: rows.__setitem__(slice(None), [r for r in rows if r.get('series')!='S373-LIFETIME-MR-500' or r['event']!='pixel-capture']))
rejected('retained open session', lambda rows,_: [r for r in rows if r['event']=='retired-consumers'][-1]['sessions'][-1].__setitem__('open',True))
rejected('uncancelled consumer token', lambda rows,_: [r for r in rows if r['event']=='retired-consumers'][-1]['sessions'][-1].__setitem__('cancelled',False))
rejected('viewer remains open', lambda _,after: after.__setitem__('elements',[{'seriesDICOMUID':'1.2.3'}]))
print('PASS: native matrix and 11 negative controls')
