#!/usr/bin/env python3
"""Orthogonal MPR opens the aligned 4D time, not pixList[0]."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def body(source, signature):
    at = 0
    while True:
        at = source.find(signature, at)
        if at < 0:
            return ''
        brace = source.find('{', at)
        semi = source.find(';', at)
        if brace >= 0 and (semi < 0 or brace < semi):
            break
        at += len(signature)
    depth, index = 0, brace
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[brace:index + 1]
        index += 1
    return ''


code = r'''
import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
}

check(FourDSeriesGuard.alignedTimeIndex(requested: 2, count: 3) == 2, "host time 2")
check(FourDSeriesGuard.alignedTimeIndex(requested: 5, count: 3) == 2, "host wrap")
check(FourDSeriesGuard.alignedTimeIndex(requested: -1, count: 3) == 2, "negative wrap")
check(FourDSeriesGuard.alignedTimeIndex(requested: 0, count: 3) == 0, "time 0 stays 0")
check(FourDSeriesGuard.alignedTimeIndex(requested: 7, count: 0) == 0, "empty series opens time 0")
print("PASS: Orthogonal MPR open uses the same wrap as SR")
'''
with tempfile.TemporaryDirectory(prefix='horos-ortho-mpr-time-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/FourDSeriesGuard.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)

viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
open_mpr = body(viewer, '- (OrthogonalMPRViewer *)openOrthogonalMPRViewer')
check(open_mpr, 'openOrthogonalMPRViewer is missing')
check('alignedTimeIndexRequested' in open_mpr or 'wrappedIndex' in open_mpr,
      'openOrthogonalMPRViewer must wrap the host 4D time')
check('initWithPixList:pixList[0]' not in open_mpr,
      'openOrthogonalMPRViewer must not pass pixList[0] to OrthogonalMPRViewer')
check('pixList[time]' in open_mpr and 'fileList[time]' in open_mpr
      and 'volumeData[time]' in open_mpr,
      'pixList, fileList and volumeData must share the wrapped time')
check('FindViewer :@"OrthogonalMPR" :pixList[0]' in open_mpr,
      'FindViewer may still identify the series by pixList[0]')

open_petct = body(viewer, '- (OrthogonalMPRPETCTViewer *)openOrthogonalMPRPETCTViewer')
check('fusionOverlayIndexForHostTime' in open_petct,
      'PET-CT overlay pin from #476 must stay')
check('alignedTimeIndexRequested' in open_petct,
      'PET-CT host wrap from #476 must stay')

blend = body(viewer, '-(void) ActivateBlending:(ViewerController*) bC')
check('fourDFusionRefusalReason' in blend or 'refuseFourDFusionWithTitle' in blend
      or 'fusionRefusalHostTimes' in blend,
      'ActivateBlending fusion refusal from #464 must stay')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: Orthogonal MPR opens one aligned 4D time')
