#!/usr/bin/env python3
"""Curved MPR opens on the curve tool and concludes through the Swift session."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
controller = (root / 'Horos/Sources/CPRController.m').read_text(encoding='latin1')
view = (root / 'Horos/Sources/CPRMPRDCMView.m').read_text(encoding='latin1')
path = (root / 'Horos/Sources/CPRCurvedPath.m').read_text(encoding='latin1')
resolution = (root / 'Horos/Sources/VRView.mm').read_text(encoding='latin1')
needed_controller = [
    'selectCurvedPathDrawingTool',
    'tCurvedROI',
    'selectCellWithTag: tCurvedROI',
    'setToolIndex: tCurvedROI',
]
missing = [item for item in needed_controller if item not in controller]
if missing:
    print('FAIL: CPRController is missing', ', '.join(missing), file=sys.stderr)
    sys.exit(1)
if 'setToolIndex: tWL' in controller and 'selectCurvedPathDrawingTool' not in controller.split('showWindow:')[1][:2500]:
    print('FAIL: showWindow still applies WL/WW after the XIB selection', file=sys.stderr)
    sys.exit(1)
show = controller[controller.index('- (void) showWindow:(id) sender'):
                  controller.index('- (void) showWindow:(id) sender') + 3500]
if 'selectCurvedPathDrawingTool' not in show:
    print('FAIL: showWindow does not select the curve tool', file=sys.stderr)
    sys.exit(1)
needed_view = [
    'HorosCurvedMPRPathSession',
    'addPatientNodeX',
    'complete',
    'tCurvedROI',
]
missing_view = [item for item in needed_view if item not in view]
if missing_view:
    print('FAIL: CPRMPRDCMView is missing', ', '.join(missing_view), file=sys.stderr)
    sys.exit(1)
if 'assert(N3VectorIsZero(node) == false)' in path:
    print('FAIL: CPRCurvedPath still aborts on a patient-space origin node', file=sys.stderr)
    sys.exit(1)
if 'diagnoseViewportWorldLength' not in resolution:
    print('FAIL: getResolution must keep the warning and name the geometric cause', file=sys.stderr)
    sys.exit(1)
if 'no viewport yet' not in resolution:
    print('FAIL: getResolution must not hide the zero-length viewport warning', file=sys.stderr)
    sys.exit(1)
print('PASS: Curved MPR starts on tCurvedROI, completes via Swift, origin is drawable')
