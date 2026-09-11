#!/usr/bin/env python3
"""VR, crop and scissors consume VTK display pixels, not AppKit frame points."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


volume = strip((root / 'Horos/Sources/VRView.mm').read_bytes().decode('latin1'))
stereo = strip((root / 'Horos/Sources/VRView+StereoVision.mm').read_bytes().decode('latin1'))
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
geometry = (root / 'Horos/Sources/VTKRetinaGeometry.swift').read_text()
interaction = (root / 'Horos/Sources/VRInteractionGeometry.swift').read_text()
curved = (root / 'Horos/Sources/CPRController.m').read_text()
path = (root / 'Horos/Sources/CurvedMPRPath.swift').read_text()


def need(condition, message):
    if not condition:
        failures.append(message)


need('HorosVTKRetinaGeometry' in geometry, 'VTKRetinaGeometry must keep its ObjC name')
need('displaySizeOfView' in geometry, 'display size must be backing pixels')
need('backingPoint' in interaction, 'window-to-view backing conversion must remain')
need('HorosVTKRetinaGeometry displaySizeOfView' in volume,
     'VRView window-center and clip-range math must use displaySizeOfView')
need('HorosVTKRetinaGeometry resizeHandleDisplayThreshold' in volume,
     'The viewport resize corner must be 20 points in display pixels')
need('HorosVTKRetinaGeometry scissorsDragThreshold' in volume,
     'Scissors sampling must use a point threshold converted to display pixels')
need('HorosVRInteractionGeometry backingPoint' in volume,
     'VR mouse paths must keep the #258 backing conversion')
need('croppingBox->On()' in volume and 'croppingBox->Off()' in volume,
     'Crop remains a vtkBoxWidget, not a 2D matrix clip')
need('setCurrentTool: t3DRotate' in volume, 'Enabling crop must keep the 3D rotate tool')
need('HorosVTKRetinaGeometry displaySizeOfView' in stereo,
     'Stereo VR must use the same display size for window-center reset')
need('HorosVTKRetinaGeometry scissorsDragThreshold' in stereo,
     'Stereo scissors must use the same display-pixel drag threshold')
need('VTKRetinaGeometry.swift' in project, 'The new Swift file must be in the app target')
need('selectCurvedPathDrawingTool' in curved, 'Do not drop Curved MPR tool selection')
need('HorosCurvedMPRPathSession' in path, 'Do not drop CurvedMPRPath')
need('SetClippingPlanes' in volume, 'Crop must still clip the volume through vtkPlanes')

if failures:
    print('FAIL:')
    print('\n'.join(failures))
    sys.exit(1)
print('PASS: VR/stereo crop and scissors use VTK display pixels; Curved MPR untouched')
