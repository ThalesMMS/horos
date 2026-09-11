#!/usr/bin/env python3
"""The documented GSPS subset is the DICOM object, not the series zoom/window."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
failures = []
subset = (root / 'docs/gsps-subset.md').read_text()
code = (root / 'Horos/Sources/GSPSDocument.swift').read_text()
for needle in (
    '1.2.840.10008.5.1.4.1.1.11.1',
    'ReferencedSOPInstanceUID',
    'PIXEL',
    'DISPLAY',
    'Softcopy VOI',
    'Displayed Area',
):
    if needle not in subset or needle not in code:
        failures.append('the documented GSPS subset no longer states %r' % needle)
if 'updatePresentationStateFromSeries' not in (root / 'docs/gsps-validation.md').read_text():
    failures.append('the validation record no longer distinguishes Horos series state from GSPS')
for failure in failures:
    print('FAIL:', failure)
if failures:
    sys.exit(1)
print('ok: the documented GSPS subset is the DICOM presentation state, not series zoom/window')
