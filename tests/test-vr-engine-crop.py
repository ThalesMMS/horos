#!/usr/bin/env python3
"""An engine switch keeps the crop in place, a saved camera's included (#668).

setCamera: puts a camera's six crop planes on the mapper and hides the crop
widget without moving it. Every engine switch goes through instantiateEngine:,
which ended by executing the crop callback: the callback re-applied the
widget's planes - the whole box, or the last crop made by hand - and a
camera's crop was lost at every switch, including the switch to the CPU that
prepareFullDepthCapture makes. Fusing a series (setBlendingEngine:) did the
same. Checked here:

* instantiateEngine: holds the crop the mapper has before the switch and puts
  it on the new engine's mappers, and runs the callback only when there is no
  crop yet;
* setBlendingEngine: gives a fused series the crop in place, not the widget's;
* the crop is copied into each mapper's own collection - VTK refills a
  mapper's collection in place, so a shared one would move every crop at once.

`<git revision>` as an optional argument reads the source from that revision,
the negative control.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/VRView.mm'
source = (subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]) if len(sys.argv) > 1
          else (root / path).read_bytes()).decode('latin1')


def method(signature):
    start = source.find(signature)
    if start < 0: return ''
    depth, index = 0, source.index('{', start)
    while True:
        if source[index] == '{': depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0: return source[start:index + 1]
        index += 1


failures = []
engine = method('- (void) instantiateEngine: (int) e')
blending = method('- (void) setBlendingEngine: (long) engineID showWait:(BOOL) showWait')
apply = method('- (void) applyCropPlanes: (vtkPlaneCollection*) crop')

held = engine.find('vtkPlaneCollection *crop = volume && volume->GetMapper() ? volume->GetMapper()->GetClippingPlanes() : NULL;')
switch = engine.find('switch( e)')
if held < 0 or switch < 0 or held > switch:
    failures.append('instantiateEngine: does not hold the crop the mapper has before the switch')
if not re.search(r'if\( crop\)\s*\[self applyCropPlanes: crop\];\s*else if\( cropcallback\)\s*cropcallback->Execute\( croppingBox, 0, nil\);', engine):
    failures.append('instantiateEngine: re-applies the widget\'s planes over the crop in place')
if engine.count('crop->Register( NULL);') != 1 or engine.count('crop->UnRegister( NULL);') != 1:
    failures.append('instantiateEngine: does not keep the held crop alive across the switch, or leaks it')
if not re.search(r'vtkPlaneCollection \*crop = volume && volume->GetMapper\(\) \? volume->GetMapper\(\)->GetClippingPlanes\(\) : NULL;\s*'
                 r'if\( crop\)\s*\[self applyCropPlanes: crop\];\s*else if\( cropcallback\)', blending):
    failures.append('setBlendingEngine: gives a fused series the widget\'s planes, not the crop in place')
for mapper in ('volumeMapper', 'textureMapper', 'blendingVolumeMapper', 'blendingTextureMapper'):
    if 'if( %s) %s->SetClippingPlanes( planes);' % (mapper, mapper) not in apply:
        failures.append('the crop does not reach ' + mapper)
if 'SetClippingPlanes( crop)' in apply or 'vtkPlanes *planes = vtkPlanes::New();' not in apply:
    failures.append('the mappers share one plane collection instead of their own copies')

if failures:
    for failure in failures:
        print('FAIL: ' + failure)
    sys.exit(1)
print('ok: an engine switch and a fusion keep the crop in place, a saved camera\'s included (#668)')
