#!/usr/bin/env python3
"""PET-CT fusion refuses an overlay whose 4D time count cannot share the host index."""
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

check(FourDSeriesGuard.fusionRefusal(hostTimes: 3, overlayTimes: 1) == nil,
      "static overlay is allowed")
check(FourDSeriesGuard.fusionOverlayIndex(hostTime: 2, hostCount: 3, overlayCount: 1) == 0,
      "static overlay stays at time 0")
check(FourDSeriesGuard.fusionOverlayIndex(hostTime: -1, hostCount: 3, overlayCount: 1) == 0,
      "static overlay ignores a wrapped host time")

check(FourDSeriesGuard.fusionRefusal(hostTimes: 3, overlayTimes: 3) == nil,
      "matched 4D overlay is allowed")
check(FourDSeriesGuard.fusionOverlayIndex(hostTime: 5, hostCount: 3, overlayCount: 3) == 2,
      "matched overlay shares the host wrap")
check(FourDSeriesGuard.fusionOverlayIndex(hostTime: -1, hostCount: 3, overlayCount: 3) == 2,
      "matched overlay wraps backward with the host")

let empty = FourDSeriesGuard.fusionRefusal(hostTimes: 3, overlayTimes: 0)!
check(empty.contains("1"), empty)
check(empty.lowercased().contains("frame") || empty.lowercased().contains("no"), empty)
check(FourDSeriesGuard.fusionOverlayIndex(hostTime: 2, hostCount: 3, overlayCount: 0) == 0,
      "empty overlay does not index -1")

let mismatch = FourDSeriesGuard.fusionRefusal(hostTimes: 3, overlayTimes: 2)!
check(mismatch.contains("2") && mismatch.contains("3"), mismatch)
check(mismatch.lowercased().contains("time"), mismatch)

print("PASS: fusion overlay index and time-count refusal")
'''
with tempfile.TemporaryDirectory(prefix='horos-four-d-fusion-') as tmp:
    p = Path(tmp)
    (p / 'main.swift').write_text(code)
    subprocess.run([
        'xcrun', 'swiftc',
        str(root / 'Horos/Sources/FourDSeriesGuard.swift'),
        str(p / 'main.swift'), '-o', str(p / 'test')
    ], check=True)
    subprocess.run([str(p / 'test')], check=True)

viewer = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
header = (root / 'Horos/Sources/ViewerController.h').read_bytes().decode('latin1')
swift = (root / 'Horos/Sources/FourDSeriesGuard.swift').read_text(encoding='utf-8')

check('fusionRefusalHostTimes' in swift or 'fusionRefusal(hostTimes' in swift,
      'FourDSeriesGuard must name a fused overlay with the wrong number of times')
check('fourDFusionRefusalReason' in header,
      'ViewerController must expose the fusion 4D refusal')

blend = body(viewer, '-(void) ActivateBlending:(ViewerController*) bC')
check('fourDFusionRefusalReason' in blend or 'refuseFourDFusionWithTitle' in blend
      or 'fusionRefusalHostTimes' in blend,
      'ActivateBlending must refuse a 4D overlay that cannot share the host times')
check('PET-CT Fusion' in blend or 'refuseFourDFusionWithTitle' in blend,
      'ActivateBlending must keep the PET-CT Fusion title on refusal')

mpr = body(viewer, '-(IBAction) orthogonalMPRViewer:(id) sender')
check('refuseFourDFusionWithTitle' in mpr or 'fourDFusionRefusalReason' in mpr,
      'orthogonalMPRViewer must refuse fusion 4D before opening PET-CT')
check('fileList[curMovieIndex]' not in mpr,
      'orthogonalMPRViewer must not index fileList with an unwrapped curMovieIndex')
check('alignedTimeIndexRequested' in mpr or 'wrappedIndex' in mpr,
      'PET-CT title must wrap the 4D time into 0 ..< maxMovieIndex')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: PET-CT fusion refuses mismatched 4D overlays and wraps the title time')
