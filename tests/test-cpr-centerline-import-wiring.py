#!/usr/bin/env python3
"""CPR load-path accepts a patient-space xyz file without replacing Curved MPR."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
controller = (root / 'Horos/Sources/CPRController.m').read_text(encoding='latin1')
header = (root / 'Horos/Sources/CPRController.h').read_text(encoding='latin1')
swift = (root / 'Horos/Sources/CPRCenterlineImport.swift').read_text()
path_session = (root / 'Horos/Sources/CurvedMPRPath.swift').read_text()
needed = [
    'importPatientSpaceCenterlineFromFile',
    'HorosCPRCenterlineImport',
    'importPatientSpaceText',
    'addPatientNode',
    'curvedPathCreationMode = NO',
]
missing = [item for item in needed if item not in controller]
if missing:
    print('FAIL: CPRController is missing', ', '.join(missing), file=sys.stderr)
    sys.exit(1)
if 'importPatientSpaceCenterlineFromFile' not in header:
    print('FAIL: CPRController.h does not declare the patient-space import', file=sys.stderr)
    sys.exit(1)
load = controller[controller.index('-(void) loadBezierPathFromFile:'):
                  controller.index('-(void) loadBezierPathFromFile:') + 1800]
if 'importPatientSpaceCenterlineFromFile' not in load:
    print('FAIL: loadBezierPathFromFile does not fall through to xyz import', file=sys.stderr)
    sys.exit(1)
if 'isKindOfClass:[CPRCurvedPath class]' not in load:
    print('FAIL: archive load must still require a CPRCurvedPath', file=sys.stderr)
    sys.exit(1)
open_panel = controller[controller.index('- (IBAction) loadBezierPath:'):
                        controller.index('- (IBAction) loadBezierPath:') + 800]
for ext in ('curvedPath', 'txt', 'xyz', 'csv'):
    if ext not in open_panel:
        print('FAIL: loadBezierPath panel is missing', ext, file=sys.stderr)
        sys.exit(1)
if 'selectCurvedPathDrawingTool' not in controller:
    print('FAIL: patient-space import must not remove the Curved MPR tool selection', file=sys.stderr)
    sys.exit(1)
if 'CurvedMPRPathSession' not in swift or 'addPatientNodeX' not in swift:
    print('FAIL: import must reuse the interactive path session', file=sys.stderr)
    sys.exit(1)
if 'origin in patient space is a drawable node' not in path_session and 'Origin is valid' not in path_session:
    if 'NaN is not' not in path_session:
        print('FAIL: CurvedMPRPath.swift contract was rewritten', file=sys.stderr)
        sys.exit(1)
print('PASS: xyz import is wired through loadBezierPath; Curved MPR session remains')
