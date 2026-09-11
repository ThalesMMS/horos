#!/usr/bin/env python3
"""Host volume uses Swift physical trapezoid; mesh decimation does not."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
controller = (root / 'Horos/Sources/ViewerController.m').read_text(encoding='latin1')
volume = (root / 'Horos/Sources/ROIVolume.mm').read_text(encoding='latin1')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
xib = (root / 'Horos/Resources/en.lproj/Viewer.xib').read_text(encoding='latin1', errors='replace')
start = controller.index('- (float) computeVolume:(ROI*) selectedRoi points:(NSMutableArray**) pts generateMissingROIs:(BOOL) generateMissingROIs generatedROIs:(NSMutableArray*) generatedROIs computeData:(NSMutableDictionary*) data error:(NSString**) error')
method = controller[start:controller.index('-(void) updateVolumeData:')]
needed = [
    'HorosROIVolumeGeometry volumeFromSlices',
    'HorosROIPatientPoint',
    'interpolateMissing: NO',
    'pic.originX',
    'pic.originY',
    'pic.originZ',
    'componentCount: imageCount',
    'roiMorphingBetween:',
    'generateMissingROIs',
    'Display-only decimation',
    'MAXPOINTS',
]
missing = [item for item in needed if item not in method]
if missing:
    print('FAIL: computeVolume is missing', ', '.join(missing), file=sys.stderr)
    sys.exit(1)
if 'location = x * sliceInterval' in method:
    print('FAIL: computeVolume still locates slices by index × sliceInterval', file=sys.stderr)
    sys.exit(1)
if 'Only ONE ROI per image supported' in method:
    print('FAIL: computeVolume still rejects disconnected components on one slice', file=sys.stderr)
    sys.exit(1)
if 'stringTex' in method or 'HorosROILabelPresentation' in method:
    print('FAIL: volume must not touch the #227/#245 label matrix', file=sys.stderr)
    sys.exit(1)
if 'HorosROIVolumeGeometry volumeFromSlices' not in volume:
    print('FAIL: ROIVolume.mm does not use the documented Swift volume', file=sys.stderr)
    sys.exit(1)
if 'sliceLocation' in volume and 'HorosROIVolumeGeometry' not in volume:
    print('FAIL: ROIVolume.mm still volumes from sliceLocation alone', file=sys.stderr)
    sys.exit(1)
if 'ROIVolumeGeometry.swift' not in pbx:
    print('FAIL: ROIVolumeGeometry.swift is not in the app target', file=sys.stderr)
    sys.exit(1)
if 'computeVolume' in xib:
    print('FAIL: Viewer.xib must stay untouched', file=sys.stderr)
    sys.exit(1)
print('PASS: computeVolume and ROIVolume use IPP trapezoid; gaps stay explicit; mesh is display-only')
