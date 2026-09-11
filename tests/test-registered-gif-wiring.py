#!/usr/bin/env python3
"""The comparison GIF is made of the viewer's own captures (#384 B).

Source-level contract:

- the companion is the fused series from `blendingController`, the product of
  the Fusion dialog, and the blend is the host's own blend slider — no second
  renderer, no second registration and no viewer picked by name or order;
- the blend the user had is restored in a `@finally`, so a capture that fails
  part-way leaves the viewer where it was;
- captures that arrive after the comparison moved are refused, not encoded;
- the animation reaches the clipboard as data through the shared policy: no
  temporary file is written, so none can be left behind or left invalid;
- the menu item, the Italian and Spanish strings and the Xcode membership are
  in place;
- and it stands in for none of the exports that have their own acceptance:
  fused DICOM (#142), movie/codec (#147), flythrough (#222), drag file
  promises (#270).
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
bridge = (root / 'Horos/Sources/RegisteredGIFHostBridge.m').read_text()
header = (root / 'Horos/Sources/RegisteredGIFHostBridge.h').read_text()
policy = (root / 'Horos/Sources/RegisteredGIFExport.swift').read_text()
app = (root / 'Horos/Sources/AppController.m').read_bytes().decode('latin1')
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
italian = (root / 'Horos/Resources/it-IT.lproj/Localizable.strings').read_text()
spanish = (root / 'Horos/Resources/es.lproj/Localizable.strings').read_text()

# The comparison is the host's fusion, not a second one.
assert 'ViewerController *fused = [self blendingController];' in bridge, \
    'the companion must be the fused series of the Fusion dialog'
assert '[self horosRegistrationSession]' in bridge, 'the session is the one #378 publishes'
for forbidden in ('get2DViewers', 'patientName', 'BrowserController', 'CGContext', 'MTLDevice', 'vtk'):
    assert forbidden not in bridge, 'the bridge must not reach for ' + forbidden
assert '[[self imageView] nsimage:NO]' in bridge, 'the frames are the captures the viewer already draws'
assert 'NSSlider *slider = [self blendingSlider];' in bridge and 'sliderFusion' not in bridge, \
    'the blend is the Fusion panel blend slider, not the slab thickness slider'

# The viewer goes back to where the user left it, even when a capture fails.
finally_block = bridge[bridge.index('@finally'):bridge.index('@finally') + 260]
assert 'setDoubleValue:previous' in finally_block and 'blendingSlider:slider' in finally_block, \
    'the blend the user had must be restored in the @finally, not only on success'
assert bridge.index('@try') < bridge.index('nsimage:NO'), 'the capture loop runs inside the @try'

# Captures from a comparison that moved are not this comparison.
assert 'refusalForApplyingPlan:plan toSession:' in bridge, \
    'a comparison that changed while being captured must refuse its captures'
assert bridge.index('refusalForApplyingPlan') > bridge.index('@finally'), \
    'the check belongs after the captures, which is when the change can have happened'

# The clipboard route is a data route.
assert 'copyData:result.data toPasteboard:[NSPasteboard generalPasteboard]' in bridge, \
    'the animation goes to the general pasteboard through the shared policy'
for forbidden in ('NSTemporaryDirectory', 'writeToFile', 'NSSavePanel', 'createFileAtPath'):
    assert forbidden not in bridge, 'the clipboard route must not write a file: ' + forbidden
assert 'writesTemporaryFiles() -> Bool { false }' in policy

# A panel-free core, so the capture can be exercised without a modal answer.
assert 'horosRegisteredComparisonGIFWithBlendStops:' in header and 'refusal:(NSString **)refusal' in header, \
    'the capture must be callable without a panel'
core = bridge[bridge.index('- (HorosRegisteredGIFResult *)horosRegisteredComparisonGIF'):bridge.index('- (IBAction)copyRegisteredComparisonGIF:')]
for forbidden in ('NSAlert', 'runModal', 'NSPasteboard'):
    assert forbidden not in core, 'the panel-free core must not ' + forbidden

# Menu, catalogs, project.
assert 'installRegisteredGIFMenuItems' in app and 'RegisteredGIFHostBridge.h' in app, 'the menu item must be installed'
assert '@selector(copyROIsFromFusedSeries:)' in bridge, 'the item sits with the other fusion items'
assert 'item.target = nil' in bridge, 'the item goes to the front viewer through the responder chain'
for catalog, language in ((italian, 'it-IT'), (spanish, 'es')):
    for key in ('Copy Registered Comparison as GIF', 'The Comparison Was Not Copied',
                'The registered comparison could not be copied to the clipboard.'):
        assert '"%s"' % key in catalog, '%s is missing from %s' % (key, language)
assert sum('RegisteredGIFHostBridge.m' in line for line in project.splitlines()) == 4, \
    'RegisteredGIFHostBridge.m is not fully registered in the Xcode project'
assert sum('RegisteredGIFExport.swift' in line for line in project.splitlines()) == 4, \
    'RegisteredGIFExport.swift is not fully registered in the Xcode project'

# It replaces nothing that has its own acceptance.
for name in ('replacesFusedDICOMExport', 'replacesMovieExport', 'replacesFlythrough', 'replacesDragFilePromises'):
    assert '%s() -> Bool { false }' % name in policy, name + ' must stay false'
for other in ('QuicktimeExport', 'DICOMExport', 'flythrough', 'filePromise'):
    assert other not in bridge, 'the comparison GIF must not take over ' + other

print('PASS: the comparison GIF is the viewer\'s own captures at the host\'s own blend, restored in a @finally, '
      'refused when the comparison moved, and copied to the clipboard as data with no file written')
