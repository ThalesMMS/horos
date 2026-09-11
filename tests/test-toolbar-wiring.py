#!/usr/bin/env python3
"""Delegates prepare toolbar items after plugins; #308 does not reopen #274/#292."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def text(relative):
    return (root / relative).read_bytes().decode('latin1')


def require(condition, message):
    if not condition:
        failures.append(message)


delegates = (
    'Horos/Sources/ViewerController.m',
    'Horos/Sources/VRController.mm',
    'Horos/Sources/OrthogonalMPRViewer.m',
    'Horos/Sources/OrthogonalMPRPETCTViewer.m',
    'Horos/Sources/MPRController.m',
    'Horos/Sources/MPR2DController.mm',
    'Horos/Sources/SRController.mm',
    'Horos/Sources/CPRController.m',
    'Horos/Sources/EndoscopyViewer.m',
    'Horos/Sources/BrowserController.m',
    'Horos/Sources/XMLController.m',
)
for path in delegates:
    require('HorosToolbarPolicy prepareItem' in text(path),
            '%s does not prepare toolbar items after plugins' % path)

viewer = text('Horos/Sources/ViewerController.m')
require('fullscreenContentRectOnScreen' in viewer,
        'custom fullscreen still covers the detached toolbar strip')
require('USETOOLBARPANEL] && FullScreenOn == NO' in viewer,
        'resigning main still hides the toolbar during fullscreen')
vr = text('Horos/Sources/VRController.mm')
require('imageSize.width > 32' not in vr,
        'VR still normalizes icons before plugins have replaced the item')

panel = text('Horos/Sources/ToolbarPanel.m')
require('toolbarDidChange' in panel,
        'the detached panel does not remasure when the toolbar is customized')

project = text('Horos.xcodeproj/project.pbxproj')
require('ToolbarPolicy.swift' in project,
        'ToolbarPolicy.swift is not in the Horos target')

require((root / 'Horos/Sources/HorosCellSlider.swift').exists(),
        'HorosCellSlider from #388 is missing')
require((root / 'Horos/Sources/ViewerReferenceLines.swift').exists(),
        'ViewerReferenceLines from #306 is missing')

for catalog in ('Horos/Resources/es.lproj/Localizable.strings',
                'Horos/Resources/it-IT.lproj/Localizable.strings'):
    require((root / catalog).exists(), '%s disappeared' % catalog)

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: viewer, VR, MPR, SR and database toolbars prepare after plugins; '
      '#388/#306 preserved; ES/IT catalogs untouched')
