#!/usr/bin/env python3
"""Both halves of an import say how much they took and how long it cost.

Indexing happens on two paths: a mounted volume goes through
`-[DicomDatabase scanAtPath:isVolume:]`, and everything the listener or a drop
leaves behind goes through `-[DicomDatabase importFilesFromIncomingDir:…]`.
The first was given a tally and a phase timing; the second returned a count to
its caller and wrote nothing down, so a local import could not be compared with
a medium at all.

Measured on the same 1200-instance dataset (8 series of 256x256 CT, 155 MB, plus
five damaged files), once through the incoming folder on the internal disk and
once from a mounted HFS+ image with the index unused, so both open every file:

    (importFilesFromIncomingDir): 1201 file(s) taken from the incoming folder,
                                  1200 indexed, in 1.4 s (1.2 ms per file)
    (scanAtPath): HOROSCD: 3.0 s in all - 2.4 s copying 1200 files,
                  276 ms indexing 1201 files, 243 ms reading 1207 files,
                  5 ms listing 1210 files (2 ms per instance)

Both end at 1 study, 8 series, 1200 images.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
scan = (root / 'Horos/Sources/DicomDatabase+Scan.mm').read_bytes().decode('latin1')

live = re.sub(r'//[^\n]*', '', database)
at = live.find('importFilesFromIncomingDir):')
if at < 0:
    failures.append('a local import says nothing about what it took or how long it took')
else:
    line = live[max(0, at - 400):at + 600]
    if 'filesArray.count' not in line:
        failures.append('the local import does not say how many files it took')
    if 'addedFilesCount' not in line:
        failures.append('the local import does not say how many it indexed')
    if 'startTime' not in line:
        failures.append('the local import does not say how long it took')
    if 'per file' not in line:
        failures.append('the local import gives no rate, so one medium cannot be compared with '
                        'another')
    if 'if( filesArray.count)' not in line:
        failures.append('a pass that found nothing still writes a line')

# The medium half has to keep saying the same things, or the two are not comparable.
mount = re.sub(r'//[^\n]*', '', scan)
for needed in ('file(s) on the medium', 'instance(s) to take', 'HorosMediaScanTiming'):
    if needed not in mount:
        failures.append('the medium import no longer reports %r' % needed)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: a local import and a medium import both report what they took, what they indexed and '
      'what it cost')
