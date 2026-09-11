#!/usr/bin/env python3
"""File > Print reaches the viewer, not AppKit's view drawing (#610).

The origin's blank Planar pages came from a focused image view that inherited
`NSView.print:`: AppKit took the command first and tried to print a Metal layer
as an ordinary view. This checks the same property here, at the source and in
the built binary, so it cannot regress quietly.

    python3 tests/test-planar-print-responder.py [<git revision>]

This is an equivalence check, so it passes at earlier revisions too: the
property it protects was already true before the adoption phase, which is why
#610 recorded evidence instead of writing a patch. A revision argument is there
to show that, not to produce a failure.

Which class the running binary actually resolves `print:` to is read from the
process itself by `tools/exercise-native-planar-print.py responder`, and the
numbers are recorded in `docs/issue-610-delta3-integration.md`. This file keeps
the source property that makes that resolution possible.
"""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def read(path):
    if len(sys.argv) > 1:
        return subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


def method(source, signature, terminator='\n}\n'):
    start = source.find(signature)
    if start < 0:
        return ''
    return source[start:source.find(terminator, start) + len(terminator)]


failures = []
view = read('Horos/Sources/DCMView.m')
header = read('Horos/Sources/DCMView.h')
host = read('Horos/Sources/PlanarHostRenderer.swift')
bridge = read('Horos/Sources/PlanarHostBridge.m')

# 1. The image view owns print: instead of inheriting NSView's.
printing = method(view, '- (IBAction) print:(id)sender\n')
if not printing:
    failures.append('DCMView does not implement print:; File > Print would reach NSView and print the view itself')
if '[[self windowController] print: self]' not in printing:
    failures.append('a 2D viewer does not forward Print to its window controller')
if 'is2DViewer' not in printing:
    failures.append('the forwarding does not distinguish a 2D viewer from the other users of this view')
if 'nsimage' not in printing:
    failures.append('outside a 2D viewer, Print does not build an image of the frame')

# 2. The capture the print path uses reads the composed front buffer, so the
#    planar quad is part of the page and a stale buffer cannot be printed.
readback = view.find('glReadBuffer(GL_FRONT)')
if readback < 0:
    failures.append('the capture no longer reads the front buffer the composition wrote')
elif '[self display]' not in view[max(0, readback - 1200):readback]:
    failures.append('the capture reads the buffer before drawing into it')

# 3. Neither planar backend intercepts printing, and neither publishes a target
#    the GPU is still writing.
if 'print' in host.lower().replace('printWindow', '').replace('sprint', '') and 'printView' in host:
    failures.append('the planar host renderer intercepts printing')
if 'waitUntilCompleted' not in host or 'renderer.render(into: target)' not in host:
    failures.append('a planar backend can hand over a target the GPU is still writing')
if 'horosDrawPlanarInContext' not in bridge:
    failures.append('the planar composition no longer runs inside the host draw')

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: DCMView owns print: and the capture reads the composed buffer')
