#!/usr/bin/env python3
"""Framebuffer readbacks are sized by the drawable, not by the view's bounds.

A view's bounds are in points. On a Retina display the drawable is twice that in
each direction, so a readback sized from bounds captures the lower left quarter
and calls it the whole image.
"""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
failures = []
skipped = []

# Only sources the project actually compiles are in scope.
project = (root / 'Horos.xcodeproj/project.pbxproj').read_text(errors='replace')


def compiled(path):
    return ('%s in Sources' % path.name) in project


READ = re.compile(r'glReadPixels\s*\(')
BOUNDS = re.compile(r'NSRect\s+size\s*=\s*\[self bounds\]')

scanned = 0
readers = set()
for path in sorted((root / 'Horos/Sources').rglob('*.mm')) + sorted((root / 'Horos/Sources').rglob('*.m')):
    if not compiled(path):
        continue
    scanned += 1
    text = path.read_bytes().decode('latin1')
    if not READ.search(text):
        continue
    readers.add(path.name)
    for match in READ.finditer(text):
        # Find the readback's enclosing method and see where its size came from.
        begin = max(text.rfind('\n-(', 0, match.start()), text.rfind('\n- (', 0, match.start()))
        body = text[begin:match.start()]
        if BOUNDS.search(body):
            line = text.count('\n', 0, match.start()) + 1
            failures.append('%s:%d reads the framebuffer at the size of the view bounds'
                            % (path.relative_to(root), line))

# A scan that reached nothing would pass in silence, so pin both what it walked
# and which sources are still allowed to read the framebuffer by hand: DCMView
# reads a rect it took from convertRectToBacking, and OpenGLScreenReader has its
# own explicit pixel dimensions. Anything else has to use the shared readback.
if scanned < 200:
    failures.append('only %d compiled sources were scanned; this scan is looking in the wrong place' % scanned)
BY_HAND = {'DCMView.m', 'OpenGLScreenReader.m'}
if readers != BY_HAND:
    failures.append('the sources reading the framebuffer by hand changed: %s' % sorted(readers))

# Every view that used to read the framebuffer by hand goes through the shared
# readback now; the stereo pair reads one window per eye and composes the two.
for name in ('SRView.mm', 'ROIVolumeView.mm', 'SRView+StereoVision.mm', 'VRView+StereoVision.mm'):
    text = (root / 'Horos/Sources' / name).read_bytes().decode('latin1')
    if 'HorosCopyVRFramebuffer' not in text and 'HorosCopyVRStereoFramebuffer' not in text:
        failures.append('%s no longer uses the shared readback' % name)
    if 'VRFramebufferCapture.h' not in text:
        failures.append('%s does not include the shared readback' % name)
    if READ.search(text):
        failures.append('%s still reads the framebuffer by hand' % name)

# And the readback itself takes its size from the render window.
helper = (root / 'Horos/Sources/VRFramebufferCapture.h').read_text()
if 'window->GetSize()' not in helper:
    failures.append('VRFramebufferCapture.h no longer asks the window for its size')
if 'HorosCopyVRStereoFramebuffer' not in helper:
    failures.append('VRFramebufferCapture.h no longer composes the two eyes')

# The behaviour of that readback is covered by its own test; run it here so this
# one is not purely structural.
for name in ('test-vr-framebuffer-capture.py', 'test-stereo-framebuffer-capture.py'):
    functional = subprocess.run([sys.executable, str(root / 'tests' / name)],
                                capture_output=True, text=True)
    if functional.returncode == 2:
        # That test skipped for want of something this repository does not
        # carry. Its absence is not evidence about the readback either way.
        skipped.append('%s: %s' % (name, (functional.stderr.strip().splitlines() or ['skipped'])[-1]))
    elif functional.returncode != 0:
        print(functional.stdout or functional.stderr)
        failures.append('%s: the readback does not cover its drawable' % name)
    else:
        print(functional.stdout.strip())

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
if skipped:
    # The structural half passed; the functional half could not run here.
    print('skipped: %s' % '; '.join(skipped), file=sys.stderr)
    sys.exit(2)
print('ok: %d compiled sources scanned, %d read the framebuffer by hand, none at the size of the view bounds'
      % (scanned, len(readers)))
