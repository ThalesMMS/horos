#!/usr/bin/env python3
"""Texture caches follow display color space and screen-parameter changes."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
view = (root / 'Horos/Sources/DCMView.m').read_text(encoding='latin1')
roi = (root / 'Horos/Sources/ROI.m').read_text(encoding='latin1')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
volume = root / 'Horos/Sources/ROIVolumeGeometry.swift'
line = root / 'Horos/Sources/ROILineGeometry.swift'
interslice = root / 'Horos/Sources/ROIIntersliceGeometry.swift'
enhancement = root / 'Horos/Sources/ROIEnhancement.swift'


def fail(message):
    print('FAIL:', message, file=sys.stderr)
    sys.exit(1)


if 'AnnotationPresentation.swift' not in pbx:
    fail('AnnotationPresentation.swift is not in the app target')
if 'HorosAnnotationPresentation textureCacheTokenForWindow' not in view:
    fail('DCMView annotation cache does not include the Swift color-space token')
if 'HorosAnnotationPresentation textureCacheTokenForWindow' not in roi:
    fail('ROI label cache does not include the Swift color-space token')
if 'NSApplicationDidChangeScreenParametersNotification' not in view:
    fail('DCMView does not observe display/profile changes')
if 'screenParametersChanged:' not in view:
    fail('DCMView has no screen-parameter handler')
start = view.index('- (void)screenParametersChanged:')
method = view[start:start + 1200]
if 'purgeStringTextureCache' not in method:
    fail('screen change does not purge annotation textures')
if 'updateLabelFont' not in method:
    fail('screen change does not invalidate ROI label caches')
if 'OsirixLabelGLFontChangeNotification' not in method:
    fail('screen change does not rebuild label display lists')
for path, label in (
    (volume, 'ROIVolumeGeometry.swift'),
    (line, 'ROILineGeometry.swift'),
    (interslice, 'ROIIntersliceGeometry.swift'),
    (enhancement, 'ROIEnhancement.swift'),
):
    text = path.read_text(encoding='utf-8')
    if 'AnnotationPresentation' in text:
        fail(f'{label} must stay untouched by the annotation matrix')
print('PASS: annotation/ROI caches include the color-space token and refresh on display changes')
