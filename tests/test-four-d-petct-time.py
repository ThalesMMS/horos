#!/usr/bin/env python3
"""PET-CT orthogonal opens the aligned 4D time, not pixList[0]."""
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

check(FourDSeriesGuard.alignedTimeIndex(requested: 5, count: 3) == 2, "host wrap")
check(FourDSeriesGuard.fusionOverlayIndex(hostTime: 2, hostCount: 3, overlayCount: 1) == 0,
      "static overlay stays at 0 when the host is on time 2")
check(FourDSeriesGuard.fusionOverlayIndex(hostTime: 2, hostCount: 3, overlayCount: 3) == 2,
      "matched overlay shares time 2")
check(FourDSeriesGuard.fusionOverlayIndex(hostTime: 5, hostCount: 3, overlayCount: 3)
        == FourDSeriesGuard.alignedTimeIndex(requested: 5, count: 3),
      "host and overlay share one wrap")
print("PASS: PET-CT open uses the same wrap as the title")
'''
with tempfile.TemporaryDirectory(prefix='horos-petct-time-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/FourDSeriesGuard.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)

viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
open_petct = body(viewer, '- (OrthogonalMPRPETCTViewer *)openOrthogonalMPRPETCTViewer')
check(open_petct,
      'openOrthogonalMPRPETCTViewer is missing')
check('alignedTimeIndexRequested' in open_petct or 'wrappedIndex' in open_petct,
      'openOrthogonalMPRPETCTViewer must wrap the host 4D time')
check('fusionOverlayIndexForHostTime' in open_petct,
      'openOrthogonalMPRPETCTViewer must pin the overlay with fusionOverlayIndex')
check('initWithPixList:pixList[0]' not in open_petct,
      'openOrthogonalMPRPETCTViewer must not pass pixList[0] to the PET-CT viewer')
check('fileList[0]' not in open_petct or 'FindViewer' in open_petct,
      'fileList[0] may identify the series, not the opened volume')
check('pixList[time]' in open_petct and 'fileList[time]' in open_petct
      and 'volumeData[time]' in open_petct,
      'pixList, fileList and volumeData must share the wrapped time')
check('FindViewer :@"PETCT" :pixList[0]' in open_petct,
      'FindViewer may still identify the series by pixList[0]')

blend = body(viewer, '-(void) ActivateBlending:(ViewerController*) bC')
check('fourDFusionRefusalReason' in blend or 'refuseFourDFusionWithTitle' in blend
      or 'fusionRefusalHostTimes' in blend,
      'ActivateBlending fusion refusal from #464 must stay')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: PET-CT orthogonal opens one aligned 4D time for host and overlay')
