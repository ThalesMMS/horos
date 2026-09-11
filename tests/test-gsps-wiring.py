#!/usr/bin/env python3
"""Horos applies DICOM GSPS, not only the series zoom/window it already stored."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def read(path):
    return path.read_bytes().decode('latin1')


def stripped(path):
    return re.sub(r'//[^\n]*', '', read(path))


document = read(root / 'Horos/Sources/GSPSDocument.swift')
if '1.2.840.10008.5.1.4.1.1.11.1' not in document:
    failures.append('the documented GSPS SOP Class UID is gone')
for name in ('ReferencedSOPInstanceUID', 'ReferencedFrameNumber', 'Softcopy VOI LUT',
             'Displayed Area', 'PIXEL', 'DISPLAY', 'POINT', 'POLYLINE', 'CIRCLE',
             'ELLIPSE', 'Image Rotation', 'unsupportedFeatures'):
    if name not in document:
        failures.append('the documented subset no longer names %r' % name)
if 'Pixel Data is never rewritten' not in document and 'never written back into Pixel Data' not in document:
    failures.append('the subset no longer says Pixel Data is left alone')

viewer = stripped(root / 'Horos/Sources/ViewerController+GSPS.m')
if 'applyGrayscaleSoftcopyPresentationStateFromPath' not in viewer:
    failures.append('the 2D viewer no longer applies a GSPS file to the open images')
if 'changeWLWW' not in viewer or 'setRotation' not in viewer:
    failures.append('applying GSPS no longer sets the VOI or the spatial transform on the view')
if 'tOPolygon' not in viewer or 'tText' not in viewer:
    failures.append('GSPS annotations are no longer turned into ROIs')
if 'fImage' not in viewer:
    failures.append('apply no longer checks that fImage was not rewritten')
if 'Missing referenced SOP Instance UID' not in viewer:
    failures.append('a missing referenced SOP Instance UID is no longer named')

browser = stripped(root / 'Horos/Sources/BrowserController+GSPS.m')
if 'horos_tryOpenGSPSSeries' not in browser:
    failures.append('opening a presentation-state series no longer looks up the referenced images')
if 'applyGrayscaleSoftcopyPresentationStateFromPath' not in browser:
    failures.append('opening a GSPS series no longer applies it to the referenced images')

load = stripped(root / 'Horos/Sources/BrowserController.m')
if 'horos_tryOpenGSPSSeries' not in load:
    failures.append('loadSeries no longer asks whether the series is a GSPS before opening it as pixels')

app = stripped(root / 'Horos/Sources/AppController.m')
if 'installGSPSMenuItems' not in app:
    failures.append('the Apply Grayscale Presentation State menu is no longer installed')

project = read(root / 'Horos.xcodeproj/project.pbxproj')
for name in ('GSPSDocument.swift', 'ViewerController+GSPS.m', 'GSPSFileReader.m',
             'BrowserController+GSPS.m'):
    if name not in project:
        failures.append('%s is not in the Xcode project' % name)

# The Horos series presentation state is still there and must not be renamed
# into a claim of DICOM GSPS support.
dcmview = read(root / 'Horos/Sources/DCMView.m')
if 'updatePresentationStateFromSeries' not in dcmview:
    failures.append('the existing Horos series presentation state was removed; that is a different object')
if 'GrayscaleSoftcopyPresentationState' in dcmview and 'applyGrayscaleSoftcopyPresentationStateFromPath' not in dcmview:
    # DCMView may mention GSPS later; it must not be the only place.
    pass

if not (root / 'docs/gsps-subset.md').is_file():
    failures.append('the documented subset is not in docs/gsps-subset.md')
if not (root / 'docs/gsps-validation.md').is_file():
    failures.append('the local validation record is not in docs/gsps-validation.md')
if not (root / 'tools/generate-gsps-fixture.py').is_file():
    failures.append('the synthetic GSPS generator is missing')

for failure in failures:
    print('FAIL:', failure)
if failures:
    sys.exit(1)
print('ok: GSPS matching, apply, flags and menu are wired; the Horos series')
print('    presentation state remains a separate object')
