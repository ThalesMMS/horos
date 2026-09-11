#!/usr/bin/env python3
"""Check the native parallel probe's timings and synthetic received pixel data.

Run only against the private database created by the probe, never a personal DB.
The log is local evidence and must not be committed.
"""
import argparse
import json
from pathlib import Path
import re
import numpy as np
import pydicom

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('run', type=Path, help='directory containing horos.log and db/')
parser.add_argument('--complete', action='store_true')
parser.add_argument('--limit', type=float, default=7)
args = parser.parse_args()
assert 'local-validation' in args.run.resolve().parts, 'private validation path required'
log = (args.run / 'horos.log').read_text(errors='replace')
ends = {m[0]: (float(m[1]), int(m[2]), int(m[3]), m[4]) for m in re.findall(
    r'PARALLEL_END (C-MOVE|C-GET|WADO) time=([\d.]+) received=(\d+) expected=(\d+) report=([^\n]+)', log)}
assert set(ends) == {'C-MOVE', 'C-GET', 'WADO'}, ends
assert set(re.findall(r'PARALLEL_WATCHDOG (C-MOVE|C-GET|WADO) running=0', log)) == set(ends), 'missing terminal watchdog evidence'
assert not re.search(r'PARALLEL_WATCHDOG .*running=1', log), 'worker still active'
cancel = re.search(r'PARALLEL_CANCEL time=([\d.]+)', log)
if not args.complete:
    assert cancel, 'missing cancellation event'
    for operation, (end, received, expected, report) in ends.items():
        elapsed = end - float(cancel[1])
        if elapsed >= 0:
            assert elapsed <= args.limit, (operation, elapsed)
            assert operation + ' cancelled:' in report, report
            assert str(received) in report, report
else:
    assert cancel is None
    assert {k: v[1:3] for k, v in ends.items()} == {'C-MOVE': (6, 6), 'C-GET': (6, 6), 'WADO': (3, 3)}

objects = {key: {} for key in ends}
for path in (args.run / 'db').rglob('*.dcm'):
    ds = pydicom.dcmread(path)
    operation = {'CMOVE-178': 'C-MOVE', 'CGET-27': 'C-GET', 'LOCAL-WADO': 'WADO'}[str(ds.PatientID)]
    pixels = ds.pixel_array
    if operation == 'WADO':
        expected_pixels = ((int(ds.SeriesNumber) * 1000 + int(ds.InstanceNumber) + np.arange(256)) % 4096).reshape(16, 16)
        assert np.array_equal(pixels, expected_pixels), path
    else:
        assert np.all(pixels == int(ds.InstanceNumber)), path
    objects[operation][str(ds.SOPInstanceUID)] = int(getattr(ds, 'NumberOfFrames', 1))
for operation, instances in objects.items():
    assert len(instances) == ends[operation][1], (operation, len(instances), ends[operation])
print(json.dumps({key: {'objects': len(value), 'frames': sum(value.values()),
                       'cancelSeconds': round(ends[key][0] - float(cancel[1]), 3) if cancel else None}
                  for key, value in objects.items()}, indent=2))
