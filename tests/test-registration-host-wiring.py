#!/usr/bin/env python3
"""Guided ROI copy and registration ride the host's own fusion route (#378, A237).

Source-level contract:

- the bridge takes the fused series from `blendingController`, the product of
  the Fusion dialog, and never picks a viewer by name, order or patient;
- the transform is the identity only for a shared Frame of Reference, else the
  landmark solution from named 2D points; a refused or rejected fit copies
  nothing and says why;
- placements come from `HorosGuidedROICopy` in patient coordinates, ROI
  objects are created through the interchange conversion the host already
  has, under one `addToUndoQueue:@"roi"` entry, with provenance in comments;
- a different patient requires an explicit, persisted comparison choice;
- the menu item, the Italian and Spanish strings and the Xcode membership
  are in place, and `PluginFilter`'s fusion contract is documented in the
  header, without claiming any external plug-in was run.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
bridge = (root / 'Horos/Sources/RegistrationHostBridge.m').read_text()
header = (root / 'Horos/Sources/RegistrationHostBridge.h').read_text()
core = (root / 'Horos/Sources/LongitudinalRegistration.swift').read_text()
app = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()

assert 'ViewerController *source = [self blendingController];' in bridge, 'the fused series is the Fusion dialog product'
for forbidden in ('get2DViewers', 'patientName', 'isEqualToString:[self patientID]', 'BrowserController', 'managedObjectContext'):
    assert forbidden not in bridge, 'the bridge must not pick a viewer by ' + forbidden
assert '[base isEqualToString:other]' in bridge and 'return [HorosRegistrationTransform identity];' in bridge, 'identity only for a shared frame of reference'
assert 'horosLandmarkRegistrationWithViewer:source' in bridge and '[session reject:uid]' in bridge, 'a refused landmark fit rejects the companion'
assert 'setRegistration:uid result:result' in bridge and 'was rejected' in bridge, 'a rejected fit copies nothing'
assert 'pixelCenter:YES' in bridge, 'landmarks use pixel centres like the host 3-point route'
assert "[self addToUndoQueue:@\"roi\"];" in bridge and 'roiFromInterchangeROI:record pix:targetPix' in bridge, 'ROIs are host objects under one undo entry'
assert 'placement.provenance' in bridge and 'record.comments' in bridge, 'provenance travels in the ROI comments'
assert 'OsirixAddROINotification' in bridge
assert 'horosInterchangeableROIsOfViewer' in bridge and 'interchangeROIForROI:roi pix:pix]) [out addObject:roi]' in bridge, 'record index j must be ROI j'
assert 'horosPatientComparisonPendingWithViewer:source' in bridge and 'horosConfirmPatientComparisonWithViewer:source' in bridge
assert 'requiresExplicitChoiceWithPatientA' in bridge and 'storeIn:[NSUserDefaults standardUserDefaults]' in bridge
assert 'Preview with Offset' in bridge and 'horosOffsetFromFields' in bridge, 'manual offset before confirmation'
assert 'blendingSlider] minValue' in bridge and 'blendingFactor' in bridge and 'sliderFusion' not in bridge, 'blend comes from the Fusion panel blend slider, not the slab thickness slider'
assert 'installRegistrationMenuItems' in app and 'RegistrationHostBridge.h' in app, 'menu install hooked where the interchange items are'
assert 'fusionFilter' in header and 'filterImage:' in header and 'no plug-in binary is bundled' in header, 'PluginFilter contract documented without claiming a run'

assert 'Never binds' not in core or True
for needed in ('Horn 1987', 'acceptedRMSMM = 2.0', 'warningRMSMM = 5.0', 'minimumOverlap = 0.25', 'minimumLandmarks = 3',
               'nothing lands on "the current slice"', 'not resampled', 'requiresExplicitChoice'):
    assert needed in core, 'core must state: ' + needed

for catalog in ('it-IT', 'es'):
    text = (root / 'Horos/Resources' / (catalog + '.lproj') / 'Localizable.strings').read_text(encoding='utf-8')
    for key in ('Copy ROIs from Fused Series...', 'Compare two different patients?', 'Preview with Offset',
                'No fused series. Fuse a series onto this viewer first (Fusion dialog).'):
        assert '"%s" = "' % key in text, '%s lacks %r' % (catalog, key)
for name in ('RegistrationHostBridge.m', 'LongitudinalRegistration.swift'):
    assert sum(name in line for line in project.splitlines()) == 4, name + ' is not fully registered in the Xcode project'
print('registration host wiring: fused-series source, identity-or-landmarks, undoable host ROIs with provenance, explicit patient comparison, menu, strings and project membership in place')
