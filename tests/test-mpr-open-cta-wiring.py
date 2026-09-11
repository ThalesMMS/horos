#!/usr/bin/env python3
"""3D MPR CTA crash path is gated before convertDICOMCoords (#217).

horosproject/horos#391 is a SIGSEGV in MPRDCMView.subDrawRect while
VRController.computeMinMax presents a modal during hidden-MPR init.
horosproject/horos#359 recovered after a clean profile. This test keeps
that stack attached to the Swift geometry gate and refuses Universal Binary
as a cause.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
failures = []

# Public crash from horosproject/horos#391 (Horos 3.2.2, 2018-09-18).
# Full report stays off-git; this is the crashed thread only.
EXCERPT = """
Process:               Horos [50712]
Version:               3.2.2 (20180918)
Code Type:             X86-64 (Native)
OS Version:            Mac OS X 10.13.6 (17G2307)
Crashed Thread:        0  Dispatch queue: com.apple.main-thread
Exception Type:        EXC_BAD_ACCESS (SIGSEGV)
Exception Codes:       KERN_INVALID_ADDRESS at 0x00000000c5000018
Application Specific Information:
objc_msgSend() selector name: convertDICOMCoords:toSliceCoords:pixelCenter:
Performing @selector(mprViewer:) from sender NSMenuItem
Thread 0 Crashed:: Dispatch queue: com.apple.main-thread
0   libobjc.A.dylib                objc_msgSend
1   Horos                          -[MPRDCMView subDrawRect:]
2   Horos                          -[DCMView drawRect:withContext:]
3   com.apple.AppKit               NSRunCriticalAlertPanel
4   Horos                          -[VRController computeMinMax]
5   Horos                          -[VRController initWithPix:::::style:mode:]
6   Horos                          -[MPRController initWithDCMPixList:filesList:volumeData:viewerController:fusedViewerController:]
7   Horos                          -[ViewerController openMPRViewer]
8   Horos                          -[ViewerController mprViewer:]
"""


def body(path, signature):
    source = path.read_bytes().decode('latin1')
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


def check(condition, message):
    if not condition:
        failures.append(message)


check('EXC_BAD_ACCESS' in EXCERPT and 'SIGSEGV' in EXCERPT, 'keep the 3.2.2 SIGSEGV')
check('convertDICOMCoords:toSliceCoords:pixelCenter:' in EXCERPT, 'the selector is overlay conversion')
check('mprViewer:' in EXCERPT and 'computeMinMax' in EXCERPT, 'the modal is inside MPR open')
check('Universal Binary' not in EXCERPT, 'do not pin this crash on Universal Binary')
check('X86-64' in EXCERPT, 'architecture stays as printed')

swift = (root / 'Horos/Sources/MPROpenGeometry.swift').read_text(encoding='utf-8')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
viewer = root / 'Horos/Sources/ViewerController.m'
mpr = root / 'Horos/Sources/MPRDCMView.m'
vr = root / 'Horos/Sources/VRController.mm'
scissor = (root / 'Horos/Sources/VRScissorBounds.swift').read_text(encoding='utf-8')
centerline = (root / 'Horos/Sources/CPRCenterlineImport.swift').read_text(encoding='utf-8')
curved = (root / 'Horos/Sources/CurvedMPRPath.swift').read_text(encoding='utf-8')

check('HorosMPROpenGeometry' in swift, 'Swift helper must stay @objc HorosMPROpenGeometry')
check('openingWithSliceCount:spacingX:spacingY:sliceInterval:minInterval:maxInterval:width:height:mismatchedSlices:roiCount:' in swift,
      'the #217 ten-argument opener must stay')
check('mismatchedOrientations' in swift, 'IOP coherence stays on the existing helper')
check('images do not share a single orientation' in swift,
      'mixed IOP must keep a named diagnosis')
check('MPROpenGeometry.swift in Sources' in pbx, 'the helper must be in the Horos target')
check('class VRScissorBounds' in scissor, 'VRScissorBounds must stay')
check('class CPRCenterlineImport' in centerline, 'CPRCenterlineImport must stay')
check('class CurvedMPRPathSession' in curved, 'CurvedMPRPath must stay')

# The gathering moved out of -mprViewer: so the orthogonal MPR and the CPR could
# ask the same question instead of drawing empty planes (#374, A205).
decision = body(viewer, '- (HorosMPROpenDecision*) reconstructionOpeningDecision')
check('HorosMPROpenGeometry' in decision, 'the shared decision must consult the Swift opening gate')
check('mismatchedOrientations' in decision, 'the shared decision must pass the IOP mismatch count')
check('ORIENTATION_SENSIBILITY' in decision,
      'IOP compare must use the same sensibility as isDataVolumicIn4D')

for action in ('- (IBAction) mprViewer:(id) sender',
               '-(IBAction) orthogonalMPRViewer:(id) sender',
               '- (IBAction) cprViewer:(id) sender'):
    opened = body(viewer, action)
    check('reconstructionOpeningDecision' in opened,
          '%s must ask the shared geometry decision' % action)
    check('diagnosis' in opened,
          '%s must surface the named geometry diagnosis, not an empty plane' % action)

draw = body(mpr, '- (void) subDrawRect: (NSRect) r')
check('HorosMPROpenGeometry' in draw, 'subDrawRect must consult the overlay gate')
check('canConvertSliceCoords' in draw, 'subDrawRect must not convert coords blindly')
check('vrView' in draw, 'overlay waits until the hidden VR view is attached')

minmax = body(vr, '- (void) computeMinMax')
check('shouldPresentHighDynamicPrompt' in minmax, 'hidden-MPR init must skip the high-dynamic modal')
check('noNib' in minmax, 'the skip is the hidden MPR style, not all VR')

wrapper = body(viewer,
               '- (BOOL) isDataVolumicIn4D: (BOOL) check4D checkEverythingLoaded:(BOOL) c;')
check('check4D' in wrapper and 'tryToCorrect: YES' in wrapper,
      'the two-arg volumic wrapper must keep forwarding check4D')

if failures:
    for item in failures:
        print('FAIL:', item)
    sys.exit(1)
print('ok: #391 stack stays on convertDICOMCoords during computeMinMax; MPR gate is wired')
