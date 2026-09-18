#!/usr/bin/env python3
"""The Metal reslice replaces CPU ray casting in the host's 3D MPR.

Source-level contract, so a refactor that moves the hook, drops the fallback
or forgets a catalog string fails here rather than in the application:

- `MPRDCMView` asks the bridge before CPU rendering and uses the same DCMPix
  update for either image; native pixel/geometry checks cover the result;
- the bridge refuses, with a reason, every mode the engine does not
  represent (volume rendering, fusion, RGB, a reversed stack) and never
  touches Core Data, the catalogue or the DICOM files;
- the option defaults on, its menu item exists, and the notice the
  planar path shows when Metal is paused is reused unchanged;
- every new user-visible string is in the Italian and Spanish catalogs;
- the Swift and Objective-C files are in the Xcode target.
"""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
view = (root / 'Horos/Sources/MPRDCMView.m').read_bytes().decode('latin1')
bridge = (root / 'Horos/Sources/MPRHostBridge.m').read_text()
header = (root / 'Horos/Sources/MPRHostBridge.h').read_text()
planar = (root / 'Horos/Sources/PlanarHostBridge.m').read_text()
dcmview = (root / 'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()

# Hook placement inside the non-blended branch of the reconstruction.
start = view.index('- (void) updateViewMPROnLoading:(BOOL) isLoading :(BOOL) computeCrossReferenceLines')
body = view[start:view.index('\n- (void) updateViewMPROnLoading:(BOOL) isLoading\n', start)]
hook = body.index('[self horosMPRCopyImageWidth: &w height: &h]')
assert hook < body.index('[vrView render];')
assert 'if( !imagePtr && [self frame].size.width > 0' in body
assert 'else if (!imagePtr)\n            imagePtr = [vrView imageInFullDepthWidth:' in body
for setter in ('[pix setOrigin: porigin];', '[pix setPixelSpacingX: resolution];', '[pix setOrientation: orientation];',
               '[pix setSliceThickness: [vrView getClippingRangeThicknessInMm]];'):
    assert hook < body.index(setter) < body.index('[self setWLWW: previousWL :previousWW];')
assert body.index('if( blendingView)') > hook, 'the hook belongs to the primary plane, not the fused one'
assert '#import "MPRHostBridge.h"' in view

# The bridge's refusals and what it may not touch.
for reason in ('Fusion keeps the original renderer', 'RGB planes keep the original renderer',
               'Volume rendering keeps the original renderer', 'A reversed stack keeps the original renderer',
               'RGB volumes keep the original renderer'):
    assert reason in bridge, 'missing refusal: ' + reason
assert 'clippingRangeMode < 1 || controller.clippingRangeMode > 3' in bridge, 'only MIP, MinIP and mean reach the engine'
for forbidden in ('valueForKey', 'managedObjectContext', 'DicomImage', 'DicomSeries', 'DicomDatabase', 'sourceFile'):
    assert forbidden not in bridge, 'the bridge must not reach ' + forbidden
assert 'horosSetPlanarFallbackReason' in bridge and 'horosSetPlanarFallbackReason' in planar
assert 'Original renderer (Metal paused)' in dcmview, 'the paused-renderer notice is drawn by DCMView for every subclass'
assert 'into:image error:&error]' in bridge and 'free(image);' in bridge, \
    'return an owned image for the common DCMPix update, filled by the engine and freed when the reslice fails'
assert 'plane.bytes' not in bridge, 'the plane is copied once, into the image, not through an intermediate NSData (#620)'
assert '[vrView prepareMPRGeometryWidth:width height:height]' in bridge
assert '[vrView getOrigin:position windowCentered:YES sliceMiddle:YES]' in bridge
assert 'mprVoxelToWorldTransform' in bridge and 'voxelToWorld:transform' in bridge
assert 'uploadVolume:slices width:first.pwidth height:first.pheight depth:pix.count' in bridge
assert 'volume.length < expected' in bridge and 'expected != volume.length' not in bridge, \
    'the viewer buffer may exceed the slices; only a shorter buffer is refused'
assert 'NSWindowWillCloseNotification' in bridge and 'releaseVolume' in bridge, 'closing the window must free the GPU volume'
assert 'return enabled ? enabled.boolValue : YES;' in bridge, 'Metal defaults on with a per-window override'
assert 'Use Metal in MPR' in bridge and 'toggleMPRMetal:' in bridge
assert '- (float *)horosMPRCopyImageWidth:(long *)width height:(long *)height;' in header
assert 'horosMPRReplacePixels' not in view + bridge + header

# NSView frames remain in points; VTK owns the sole backing-pixel conversion.
frame = view[view.index('- (void) checkForFrame'):view.index('- (float) displayedScaleValue')]
assert 'convertRectToBacking' not in frame
assert '[self convertRect: [self bounds] toView: nil]' in frame

# A216 on the CPR path: the curved views are DCMView subclasses whose ROI
# statistics go through -[DCMPix getROIValue:::], the one place that reads
# -computefImageForMeasurement. No CPR source may grow a measurement path of
# its own that would see the presentation filter again.
# CurvedMPR.m was here too, compiled by nothing and removed with the other dead sources (#652).
for name in sorted((root / 'Horos/Sources').glob('CPR*.m')):
    text = name.read_bytes().decode('latin1')
    for forbidden in ('getROIValue', 'computefImage', 'applyConvolutionOnImage'):
        assert forbidden not in text, '%s must not reimplement the measurement path (%s)' % (name.name, forbidden)
roi = (root / 'Horos/Sources/ROI.m').read_bytes().decode('latin1')
assert 'getROIValue:no :self :nil]' in roi, 'ROI statistics must come from DCMPix'
dcmpix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
assert 'computedfImage = [self computefImageForMeasurement];' in dcmpix

# Strings and project membership.
for catalog in ('it-IT', 'es'):
    text = (root / 'Horos/Resources' / (catalog + '.lproj') / 'Localizable.strings').read_text(encoding='utf-8')
    assert '"Use Metal in MPR" = "' in text, catalog + ' lacks the menu title'
    assert '"Original renderer (Metal paused)" = "' in text
for name in ('MPRHostBridge.m', 'MPRMetalReslicer.swift'):
    assert sum(name in line for line in project.splitlines()) == 4, name + " is not fully registered in the Xcode project"
print('mpr metal host wiring: hook, refusals, notice, strings and project membership in place')
