#!/usr/bin/env python3
"""MPR 4D time steps refresh ROI intensity caches through Swift, not #227 text."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
controller = (root / 'Horos/Sources/MPRController.m').read_bytes().decode('latin1')
view = (root / 'Horos/Sources/MPRDCMView.m').read_bytes().decode('latin1')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
helper = root / 'Horos/Sources/ROITemporalStatistics.swift'

if not helper.is_file():
    print('FAIL: ROITemporalStatistics.swift is missing', file=sys.stderr)
    sys.exit(1)
if 'ROITemporalStatistics.swift' not in project:
    print('FAIL: project.pbxproj does not compile ROITemporalStatistics.swift', file=sys.stderr)
    sys.exit(1)

start = controller.index('- (void) setCurMovieIndex: (int) m')
method = controller[start:controller.index('- (void) performMovieAnimation:', start)]
needed = [
    'Horos-Swift.h',
    'HorosROITemporalStatistics cachedValuesRemainValidWithPreviousTimeIndex',
    'previousMovieIndex',
    'geometryUnchanged: YES',
    '[r recompute]',
    'mprView1',
    'mprView2',
    'mprView3',
    'hiddenVRController setMovieFrame',
    'updateViewsAccordingToFrame',
]
missing = [item for item in needed if item not in controller]
if missing:
    print('FAIL: MPRController is missing', ', '.join(missing), file=sys.stderr)
    sys.exit(1)
for item in needed[1:]:
    if item not in method:
        print('FAIL: setCurMovieIndex does not', item, file=sys.stderr)
        sys.exit(1)
if 'stringTex' in method or 'HorosROILabelPresentation' in method:
    print('FAIL: 4D ROI values must not touch the #227/#245 label matrix', file=sys.stderr)
    sys.exit(1)

if 'Horos-Swift.h' not in view:
    print('FAIL: MPRDCMView.m does not import Horos-Swift.h', file=sys.stderr)
    sys.exit(1)
if 'mustRefreshCachedValuesAfterReconstructedBufferChange' not in view:
    print('FAIL: MPRDCMView does not refresh ROI caches after a reconstructed buffer change', file=sys.stderr)
    sys.exit(1)
if '[r recompute]' not in view and '[roi recompute]' not in view:
    print('FAIL: MPRDCMView never invalidates ROI intensity caches', file=sys.stderr)
    sys.exit(1)
if 'stringTex' in view[view.find('mustRefreshCachedValuesAfterReconstructedBufferChange'):
                       view.find('mustRefreshCachedValuesAfterReconstructedBufferChange') + 800]:
    print('FAIL: reconstructed-buffer refresh must not touch string textures', file=sys.stderr)
    sys.exit(1)

print('PASS: MPR 4D time changes invalidate ROI intensity caches through Swift')
