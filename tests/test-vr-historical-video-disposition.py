#!/usr/bin/env python3
"""The 4.0.0RC1 YouTube clip is a VR interaction film, not a crash (#211).

horosproject/horos#446 points at https://youtu.be/W4tMWAQ9Mzo. The historical
audit line VRView.mm:3156 is mouseDragged:, next to generateROI and t3DCut.
This test keeps that reading attached to the selectors the film actually
exercises, and refuses to mix Retina #29, presets #375/A034, or camera
#375/A209. The MP4 stays off-git.
"""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
failures = []

# Public labels only. The clinical CTA frames stay off-git.
VIDEO = """
id: W4tMWAQ9Mzo
title: 3D VOLUME RENDERING PROBLEM - HOROS 4.0.0RC1
upload: 20181221
duration_s: 21.08
window: 3D Reconstruction: ARTERIAL (S)
overlay: View Size: 1425 x 708
scale: 0.068 % then 0.087 %
engine: CPU
best: selected
crop: on
sha256: 2a1e07dab07331893e6bc5ebe7d9e814a08aa19d91cb328009f38d8e0d26ca74
historical: VRView.mm:3156 mouseDragged:
gestures: gray viewport, zoom, scissors t3DCut, rotate off-center
"""


def body(path, signature):
    source = path.read_bytes().decode('latin1')
    at = source.find(signature)
    if at < 0:
        return ''
    opening = source.index('{', at)
    depth, index = 0, opening
    while index < len(source):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[opening:index + 1]
        index += 1
    return ''


def check(condition, message):
    if not condition:
        failures.append(message)


# --- the clip is a 21s VR film, not a crash -----------------------------------
check('W4tMWAQ9Mzo' in VIDEO, 'YouTube id must stay attached to this reading')
check('3D VOLUME RENDERING PROBLEM' in VIDEO, 'keep the public title')
check('3D Reconstruction: ARTERIAL (S)' in VIDEO, 'keep the window title from the frames')
check('View Size: 1425 x 708' in VIDEO, 'keep the overlay size from the frames')
check('engine: CPU' in VIDEO, 'the film used the CPU engine, not GPU/Metal')
check('scissors t3DCut' in VIDEO, 'the green polygon is the scissors tool')
check('Exception Type:' not in VIDEO, 'do not relabel the film as a crash')
check('applicationDidFinishLaunching' not in VIDEO,
      'the film is not a launch hang')

doc = (root / 'docs/vr-historical-video-disposition.md').read_text()
check('W4tMWAQ9Mzo' in doc, 'the disposition must cite the YouTube id')
check('2a1e07dab07331893e6bc5ebe7d9e814a08aa19d91cb328009f38d8e0d26ca74' in doc,
      'the inspected format-18 digest must stay in the disposition')
check('142ad434b9032527c114bcc138dfb380057be699' in doc,
      'keep the historical base SHA')
check('mouseDragged:' in doc and '3156' in doc,
      'the audit line is mouseDragged, not a mystery offset')
check('dontRenderVolumeRenderingOsiriX' in doc,
      'the gray scissors flash maps to dontRenderVolumeRenderingOsiriX')
check('não há patch' in doc.lower() or 'Sem patch' in doc,
      'the disposition must refuse a speculative patch')
check('permanece aberta' in doc, 'do not treat this write-up as closing #211')
check('bundle isolado' in doc, 'the isolated-app gap must stay explicit')
check('#29' in doc and 'não a fecha nem a absorve' in doc,
      'do not fold #29 into #211')
check('3D Presets' in doc and '#375' in doc, 'do not fold presets/camera #375')
tail = doc.split('## Disposição')[-1].lower()
check('corrigido' not in tail, 'the disposition section must not call the film fixed')
check('não é correção' in tail, 'absence of a run is not a fix')
check(not re.search(r'(?i)\b(close|closes|fix|fixes)\s+#312\b', doc),
      'this document must not close epic #312')
check('Sem rebuild VTK' in doc, 'the write-up must say VTK was not rebuilt')

vr = root / 'Horos/Sources/VRView.mm'
source = vr.read_bytes().decode('latin1')
drag = body(vr, '- (void)mouseDragged:(NSEvent *)theEvent')
magnify = body(vr, '-(void) magnifyWithEvent:(NSEvent *)event')
rotate = body(vr, '-(void) rotateWithEvent:(NSEvent *)event')
roi = body(vr, '- (void) generateROI')
moved = body(vr, '-(void) mouseMoved: (NSEvent*) theEvent')

check(drag and 't3DCut' in drag and 'generateROI' in drag,
      'mouseDragged must still draw the scissors polygon through generateROI')
check(roi and 'ROI3DData' in roi, 'generateROI is gone')
check(magnify and 'eventToPlugins' in magnify and 'aCamera' not in magnify,
      'magnifyWithEvent must stay a plugin passthrough, not the film zoom')
check(rotate and 'eventToPlugins' in rotate and 'aCamera' not in rotate,
      'rotateWithEvent must stay a plugin passthrough')
check('View Size: %d x %d' in moved and '[self frame].size.width' in moved,
      'the film overlay still reads the view frame in points')
check('Scale: %2.3f' in moved and 'GetParallelProjection' in moved,
      'the film scale overlay still requires parallel projection')

# Scissors mouseDown blanks the volume mapper while the polygon is drawn.
cut_down = source.find('else if( tool == t3DCut)')
check(cut_down > 0, 't3DCut mouseDown is gone')
cut_block = source[cut_down:cut_down + 1200]
check('dontRenderVolumeRenderingOsiriX = 1' in cut_block,
      'starting scissors must still disable the volume mapper (gray view in the film)')
check('generateROI' in cut_block, 't3DCut mouseDown must still seed generateROI')
check('HorosVRInteractionGeometry backingPoint' in cut_block,
      't3DCut must keep the #258 window-to-view conversion, not a new speculative path')

# #258 conversion is present; that is not a runtime reproduction of the film.
geom = (root / 'Horos/Sources/VRInteractionGeometry.swift').read_text()
check('backingPoint' in geom, 'VRInteractionGeometry.swift is gone')

# Scissor bounds stay the #219 sanitizer, not a new VR rewrite. #29's
# VTKRetinaGeometry is a different front and is not required here.
bounds = (root / 'Horos/Sources/VRScissorBounds.swift').read_text()
check('HorosVRScissorBounds' in bounds, 'preserve VRScissorBounds')

if failures:
    for item in failures:
        print('FAIL:', item)
    sys.exit(1)
print('ok: 4.0.0RC1 film is VR interaction; mouseDragged/t3DCut mapping stays; #29/#375 stay separate')
