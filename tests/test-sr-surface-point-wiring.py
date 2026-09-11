#!/usr/bin/env python3
"""Surface Rendering 3D points pick the iso actor, not the camera focal plane."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


def method(source, name):
    at = source.find(name)
    if at < 0:
        return ''
    return source[at:source.index('\n}', at) + 2]


view = strip((root / 'Horos/Sources/SRView.mm').read_bytes().decode('latin1'))
header = (root / 'Horos/Sources/SRView.h').read_bytes().decode('latin1')
stereo = strip((root / 'Horos/Sources/SRView+StereoVision.mm').read_bytes().decode('latin1'))
project = (root / 'Horos.xcodeproj/project.pbxproj').read_bytes().decode('latin1')
helper = root / 'Horos/Sources/SRSurfacePointGeometry.swift'

if not helper.is_file():
    failures.append('Horos/Sources/SRSurfacePointGeometry.swift is missing')
if 'SRSurfacePointGeometry.swift' not in project:
    failures.append('project.pbxproj does not compile SRSurfacePointGeometry.swift')
if 'Horos-Swift.h' not in (root / 'Horos/Sources/SRView.mm').read_bytes().decode('latin1'):
    failures.append('SRView.mm does not import Horos-Swift.h')

throw = method(view, '- (void) throw3DPointOnSurface')
if not throw:
    failures.append('throw3DPointOnSurface is gone')
else:
    if 'vtkWorldPointPicker' in throw:
        failures.append('throw3DPointOnSurface still uses vtkWorldPointPicker, which lands on the focal plane')
    if 'vtkCellPicker' not in throw and 'pickSurfaceAtDisplayX' not in throw:
        failures.append('throw3DPointOnSurface does not pick the iso surface')
    if 'add3DPoint' not in throw or 'add2DPoint' not in throw:
        failures.append('a hit no longer writes both the 3D actor and the exported 2D point')

pick = method(view, '- (BOOL) pickSurfaceAtDisplayX')
if not pick:
    failures.append('pickSurfaceAtDisplayX is gone')
else:
    if 'vtkCellPicker' not in pick:
        failures.append('the surface pick does not use vtkCellPicker')
    if 'PickableOn' not in pick and 'setSurfaceActorsPickable: YES' not in pick and 'setSurfaceActorsPickable:YES' not in pick:
        failures.append('iso actors stay PickableOff during the pick, so CellPicker cannot hit them')
    if 'PickableOff' not in pick and 'setSurfaceActorsPickable: NO' not in pick and 'setSurfaceActorsPickable:NO' not in pick:
        failures.append('iso actors are left pickable, so the 3D-point tool would select the surface instead of a sphere')

convert = method(view, '- (void) convert3Dto2Dpoint')
if 'HorosSRSurfacePointGeometry' not in convert:
    failures.append('convert3Dto2Dpoint no longer uses SRSurfacePointGeometry for the exported voxel')

change = method(view, '- (void) changeActor:')
if 'PickableOff' not in change:
    failures.append('changeActor no longer leaves iso actors unpickable after reconstruction')

for source, label in ((view, 'SRView.mm'), (stereo, 'SRView+StereoVision.mm')):
    if 'throw3DPointOnSurface' not in source:
        failures.append('%s no longer places a 3D point' % label)
        continue
    at = source.find('throw3DPointOnSurface')
    window = source[max(0, at - 500):at + 80]
    if 'HorosVRInteractionGeometry backingPoint' not in window:
        failures.append('%s throws a 3D point from view points, not VTK backing pixels' % label)
    if 'vtkWorldPointPicker' in method(source, '- (void)mouseDown:'):
        failures.append('%s mouseDown still uses vtkWorldPointPicker for the surface click' % label)

if failures:
    print('FAIL:', *failures, sep='\n', file=sys.stderr)
    sys.exit(1)
print('PASS: SR 3D points pick the iso surface in backing pixels and export through SRSurfacePointGeometry')
