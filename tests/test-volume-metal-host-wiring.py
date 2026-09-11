#!/usr/bin/env python3
"""The Metal volume renderer sits beside the host's 3D viewer as an explicit comparison (#375).

Source-level contract:

- the VRView snapshot reads the VTK camera, window, CLUT table, opacity
  curve, mode, clipping range, shading and crop box, divides VTK's scaled
  frame by the view's factor, and declines RGB, fusion and the 16-bit CLUT
  with a reason;
- the controller category uploads one volume per NSData buffer, renders
  through HorosVolumeRenderer, records the reason and the milliseconds, and
  frees the GPU volume when the window closes;
- the comparison window is reached from the VRView's contextual menu, refreshes
  on the camera notification the host already posts and on a signature poll,
  and never touches Core Data, DICOM files or the catalogue;
- the new strings are in the Italian and Spanish catalogs and the files are in
  the Xcode target.
"""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
bridge = (root / 'Horos/Sources/VRHostBridge.mm').read_text()
header = (root / 'Horos/Sources/VRHostBridge.h').read_text()
window = (root / 'Horos/Sources/VolumeComparison.swift').read_text()
renderer = (root / 'Horos/Sources/VolumeMetalRenderer.swift').read_text()
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()

for needed in ('aCamera->GetPosition(position)', 'aCamera->GetParallelProjection()', 'aCamera->GetParallelScale() / factor',
               'position[i] / factor', 'clippingRangeThickness / factor', 'table[i][0] * 255', 'NSPointFromString(point)', 'pt.x - 1000',
               'volumeProperty->GetShade()', 'croppingBox->GetEnabled()', 'bounds[2 * axis] / factor'):
    assert needed in bridge, 'snapshot must read: ' + needed
for reason in ('RGB volumes keep the original renderer', 'Fusion keeps the original renderer', 'The 16-bit CLUT keeps the original renderer'):
    assert reason in bridge, 'missing refusal: ' + reason
for forbidden in ('valueForKey', 'managedObjectContext', 'DicomImage', 'DicomSeries', 'DicomDatabase', 'sourceFile', 'BrowserController'):
    assert forbidden not in bridge, 'the bridge must not reach ' + forbidden
assert 'volumeData[curMovieIndex]' in bridge and 'pixList[curMovieIndex]' in bridge, 'the volume comes from the controller\'s own buffers'
assert 'objc_getAssociatedObject(self, &uploadedKey) != volume || !renderer.isReady' in bridge, 'one upload per volume buffer'
assert 'NSWindowWillCloseNotification' in bridge and 'releaseVolume' in bridge, 'closing the window must free the GPU volume'
assert 'Compare in Metal (3D)' in bridge and 'openVolumeMetalComparison:' in bridge
assert '- (NSMenu *)menuForEvent:(NSEvent *)event' in bridge, 'the comparison is reached from the view\'s contextual menu'
assert 'HorosVolumeComparison openWithSource' in bridge
assert 'renderWithCamera:snapshot[@"camera"] near:' in bridge and 'scalarOut:scalarOut' in bridge
assert '- (NSDictionary *)horosVolumeSnapshot;' in header and 'horosVolumeMetalRenderWithWidth' in header

assert 'OsirixVRCameraDidChangeNotification' in window, 'refresh on the host camera notification'
assert 'volumeStateSignature()' in window and 'Timer.scheduledTimer' in window, 'poll the state signature for window/CLUT/opacity changes'
assert 'poll?.invalidate()' in window and 'windowWillClose' in window
for name in ('Metal Comparison', 'Original Viewer', 'Close Comparison'):
    assert name in window
assert 'VolumeRenderingMode' in renderer and 'case composite = 0, maximum = 1, minimum = 2, mean = 3' in renderer, 'mode numbers follow the host'
assert 'makeAndReturnError' not in renderer or '@objc public static func make() throws' in renderer

for catalog in ('it-IT', 'es'):
    text = (root / 'Horos/Resources' / (catalog + '.lproj') / 'Localizable.strings').read_text(encoding='utf-8')
    for key in ('Compare in Metal (3D)', 'Metal comparison, %.1f ms. Use the original viewer for tools and overlays.'):
        assert '"%s" = "' % key in text, '%s lacks %r' % (catalog, key)
for name in ('VRHostBridge.mm', 'VolumeComparison.swift', 'VolumeMetalRenderer.swift'):
    assert sum(name in line for line in project.splitlines()) == 4, name + ' is not fully registered in the Xcode project'
print('volume metal host wiring: snapshot, refusals, upload, teardown, menu, window, strings and project membership in place')
