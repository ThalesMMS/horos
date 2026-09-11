#!/usr/bin/env python3
"""Selected line ROI asks Swift for physical constructions and adds the three marks."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
controller = (root / 'Horos/Sources/ViewerController.m').read_text(encoding='latin1')
start = controller.index('- (IBAction) generateGeometryFromSelectedLine:')
method = controller[start:start + 2500]
menu = controller[controller.index('-(NSMenu*)contextualMenuForROI:(ROI*)roi\n{'):
                  controller.index('- (IBAction) generateGeometryFromSelectedLine:')]
needed = [
    'HorosROILineGeometry constructionFromLineA',
    'generateGeometryFromSelectedLine:',
    'tMesure',
    't2DPoint',
    'NSLocalizedString(@"Perpendicular"',
    'NSLocalizedString(@"Parallel"',
    'NSLocalizedString(@"Midpoint"',
    'addToUndoQueue: @"roi"',
]
missing = [item for item in needed if item not in controller]
if missing:
    print('FAIL: ViewerController is missing', ', '.join(missing), file=sys.stderr)
    sys.exit(1)
if 'generateGeometryFromSelectedLine:' not in menu:
    print('FAIL: contextual menu does not offer line geometry', file=sys.stderr)
    sys.exit(1)
if 'type == tMesure' not in menu:
    print('FAIL: ROI contextual menu does not special-case a line', file=sys.stderr)
    sys.exit(1)
if 'stringTex' in method or 'HorosROILabelPresentation' in method:
    print('FAIL: line geometry must not touch the #227/#245 label matrix', file=sys.stderr)
    sys.exit(1)
print('PASS: selected line builds perpendicular, parallel and midpoint from Swift physical geometry')
