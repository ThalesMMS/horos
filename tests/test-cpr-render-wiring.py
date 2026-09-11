#!/usr/bin/env python3
"""CPR drawRect consults the Swift lifecycle so nested display cannot hang (#204).

horosproject/horos#531 names DrawRect recursion on Xcode 10/11 SDKs. #470 hangs
with and without resample. This is not the Curved MPR path (#31), not
straightened generation (#221), not MPR CTA overlay (#217) and not the
Dental3D Z-buffer (#213).
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
mpr = (root / 'Horos/Sources/CPRMPRDCMView.m').read_text(encoding='latin1')
straight = (root / 'Horos/Sources/CPRStraightenedView.m').read_text(encoding='latin1')
stretched = (root / 'Horos/Sources/CPRStretchedView.m').read_text(encoding='latin1')
transverse = (root / 'Horos/Sources/CPRTransverseView.m').read_text(encoding='latin1')
controller = (root / 'Horos/Sources/CPRController.m').read_text(encoding='latin1')
swift = (root / 'Horos/Sources/CPRRenderLifecycle.swift').read_text(encoding='utf-8')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
curved = (root / 'Horos/Sources/CurvedMPRPath.swift').read_text(encoding='utf-8')
open_geo = (root / 'Horos/Sources/MPROpenGeometry.swift').read_text(encoding='utf-8')
zbuffer = (root / 'Horos/Sources/VRRayCastZBuffer.swift').read_text(encoding='utf-8')
failures = []

# Public hang from horosproject/horos#531: DrawRect recursion in CPR views on
# newer SDKs. No crash report was attached; the nested drawRect symbols are
# the hang, not VTK and not Universal Binary.
EXCERPT = """
Thread 0:: Dispatch queue: com.apple.main-thread
0   Horos   -[CPRMPRDCMView drawRect:]
1   Horos   -[DCMView drawRect:withContext:]
2   AppKit  -[NSView displayIfNeeded]
3   Horos   -[CPRMPRDCMView setNeedsDisplay:]
4   Horos   -[CPRMPRDCMView drawRect:]
5   Horos   -[CPRController showWindow:]
"""


def method(source, start, length=2800):
    index = source.index(start)
    return source[index:index + length]


def check(condition, message):
    if not condition:
        failures.append(message)


check('drawRect:' in EXCERPT and EXCERPT.count('drawRect') >= 2, 'keep nested drawRect in the hang stack')
check('CPRController showWindow' in EXCERPT, 'the hang is during CPR open')
check('Universal Binary' not in EXCERPT, 'do not pin this hang on Universal Binary')
check('GetZBufferValue' not in EXCERPT, 'Z-buffer is #213, not this hang')

check('drawrect-recursion' in swift, 'Swift must name nested drawRect')
check('not a number' in swift, 'NaN spacing is a named diagnosis')
check('opening-native' in swift and 'opening-resampled' in swift,
      'resampled and native opens stay distinct')
check('HorosCPRRenderLifecycle' in swift, 'Swift helper must stay @objc HorosCPRRenderLifecycle')
check('class CurvedMPRPathSession' in curved, 'CurvedMPRPath must stay')
check('class MPROpenGeometry' in open_geo, 'MPROpenGeometry must stay')
check('class RayCastZBuffer' in zbuffer or 'RayCastZBuffer' in zbuffer,
      'VRRayCastZBuffer must stay')

mpr_draw = method(mpr, '- (void) drawRect:(NSRect)rect')
for item in (
    'HorosCPRRenderLifecycle beginDrawNamed',
    'endDrawNamed',
    '@finally',
    'mpr-%d',
):
    check(item in mpr_draw, 'CPRMPRDCMView drawRect is missing %s' % item)
check('diagnoseSpacingX' in mpr, 'CPRMPRDCMView must name spacing in drawCurvedPathInGL')
check('markCurveReady' in mpr, 'concluding a curve must mark the lifecycle ready')
# Zero spacing on first open is "no viewport yet" (#31). Skipping the whole
# drawRect here would never create a viewport.
check('CPR render refused' not in mpr_draw,
      'CPRMPRDCMView drawRect must not refuse the first paint on zero spacing')
check('CPR render refused' not in straight,
      'straightened drawRect must not refuse the first paint on zero spacing')
check('CPR render refused' not in stretched,
      'stretched drawRect must not refuse the first paint on zero spacing')

straight_draw = method(straight, '- (void) drawRect:(NSRect)rect')
for item in (
    'beginDrawNamed:@"straightened"',
    'endDrawNamed:@"straightened"',
    '@finally',
    'diagnoseSpacingX',
    'shouldDisplaySynchronouslyWhileDrawing',
):
    check(item in straight, 'CPRStraightenedView is missing %s' % item)
check('_processingRequest = YES' in straight_draw, 'straightened still generates the request inside drawRect')
yes_at = straight_draw.find('_processingRequest = YES')
super_at = straight_draw.find('[super drawRect:')
no_at = straight_draw.rfind('_processingRequest = NO')
check(0 <= yes_at < super_at < no_at,
      'straightened must keep _processingRequest through super.drawRect')

for item in (
    'beginDrawNamed:@"stretched"',
    'endDrawNamed:@"stretched"',
    'diagnoseSpacingX',
    'shouldDisplaySynchronouslyWhileDrawing',
    '@finally',
):
    check(item in stretched, 'CPRStretchedView is missing %s' % item)
check('[self display]' not in stretched,
      'CPRStretchedView must not call display synchronously during drag')

for item in (
    'transverse-%',
    'endDrawNamed',
    '@finally',
    'shouldDisplaySynchronouslyWhileDrawing',
):
    check(item in transverse, 'CPRTransverseView is missing %s' % item)

show = method(controller, '- (void) showWindow:(id) sender', 3500)
close = method(controller, '- (void)windowWillClose:(NSNotification *)notification', 4000)
for item in (
    'HorosCPRRenderLifecycle reset',
    'beginOpeningResampled',
    'markOpen',
):
    check(item in show, 'showWindow is missing %s' % item)
check('beginClosing' in close and 'markClosed' in close,
      'windowWillClose does not close the CPR render lifecycle')
check('selectCurvedPathDrawingTool' in show, 'showWindow must keep the #31 curve tool')

count = pbx.count('CPRRenderLifecycle.swift in Sources */ =')
check(count == 1, 'CPRRenderLifecycle.swift must appear once in the app target, got %s' % count)

vtk = (root / 'VTK/Rendering/Volume/vtkFixedPointRayCastImage.cxx').read_text(encoding='latin1')
check('HorosCPRRender' not in vtk, 'do not patch VTK for this hang')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: CPR views gate drawRect, skip nested display, name invalid geometry, and close the window')
