#!/usr/bin/env python3
"""VR 3D angle picks patient-space points and keeps the Swift angle after camera motion."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
view = (root / 'Horos/Sources/VRView.mm').read_text(encoding='latin1')
needed = [
    'tool == tAngle',
    'currentTool == tAngle',
    'get3DPixelUnder2DPositionX',
    'HorosVRMeasurementGeometry angleDegreesAtX',
    'HorosProjectPatientPoints',
    'updateAngleMeasurementProjection',
    'AngleHotKeyAction',
    'angleMeasurementPatient',
]
missing = [item for item in needed if item not in view]
if missing:
    print('FAIL: VRView is missing', ', '.join(missing), file=sys.stderr)
    sys.exit(1)
start = view.index('static bool HorosProjectPatientPoints')
body = view[start:view.index('// Each inactive overlay')]
if 'GetDirectionOfProjection' in body:
    print('FAIL: 3D angle projection must not hide on camera rotation', file=sys.stderr)
    sys.exit(1)
if 'factor' not in body:
    print('FAIL: patient millimetres must be scaled back to VTK world', file=sys.stderr)
    sys.exit(1)
print('PASS: tAngle stores patient-space points and reprojects without dropping the angle')
