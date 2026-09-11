#!/usr/bin/env python3
"""Viewer asks Swift for projection vs 3D between t2DPoint ROIs on distinct slices."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
controller = (root / 'Horos/Sources/ViewerController.m').read_text(encoding='latin1')
header = (root / 'Horos/Sources/ViewerController.h').read_text(encoding='latin1')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
xib = (root / 'Horos/Resources/en.lproj/Viewer.xib').read_text(encoding='latin1', errors='replace')
start = controller.index('- (IBAction) measureBetweenSelectedSlices:')
method = controller[start:start + 3500]
needed = [
    'HorosROIIntersliceGeometry measureFrom',
    'measureBetweenSelectedSlices:',
    't2DPoint',
    'tText',
    'projectedDistance',
    'distance3D',
    'NSLocalizedString(@"%.2f mm projection / %.2f mm 3D (%@)"',
    'addToUndoQueue: @"roi"',
]
missing = [item for item in needed if item not in controller]
if missing:
    print('FAIL: ViewerController is missing', ', '.join(missing), file=sys.stderr)
    sys.exit(1)
if 'measureBetweenSelectedSlices:' not in header:
    print('FAIL: action is not declared on ViewerController', file=sys.stderr)
    sys.exit(1)
if 'measureBetweenSelectedSlices:' not in method:
    print('FAIL: could not isolate measureBetweenSelectedSlices:', file=sys.stderr)
    sys.exit(1)
if 'stringTex' in method or 'HorosROILabelPresentation' in method:
    print('FAIL: interslice measure must not touch the #227/#245 label matrix', file=sys.stderr)
    sys.exit(1)
menu_roi = controller[controller.index('-(NSMenu*)contextualMenuForROI:(ROI*)roi\n{'):
                      controller.index('- (IBAction) generateGeometryFromSelectedLine:')]
if 'measureBetweenSelectedSlices:' not in menu_roi:
    print('FAIL: point ROI contextual menu does not offer interslice measure', file=sys.stderr)
    sys.exit(1)
if 'type == t2DPoint' not in menu_roi:
    print('FAIL: ROI contextual menu does not special-case a 2D point', file=sys.stderr)
    sys.exit(1)
if 'measureBetweenSelectedSlices:' not in controller[controller.index('/******************* Tools menu ***************************/'):
                                                     controller.index('/******************* WW/WL menu items **********************/')]:
    print('FAIL: image contextual menu does not offer interslice measure', file=sys.stderr)
    sys.exit(1)
if 'ROIIntersliceGeometry.swift' not in pbx:
    print('FAIL: ROIIntersliceGeometry.swift is not in the app target', file=sys.stderr)
    sys.exit(1)
if 'measureBetweenSelectedSlices' in xib:
    print('FAIL: Viewer.xib must stay untouched', file=sys.stderr)
    sys.exit(1)
print('PASS: viewer measures two slice points through Swift and labels projection vs 3D')
