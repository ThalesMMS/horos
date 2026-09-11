#!/usr/bin/env python3
"""The first render no longer waits for drawRect:, and nothing is held after it.

`-[VTKView initializeVTKSupport]` runs while the nib is being unarchived, when
the view is in no window at all, so the render window was told `SetRootWindow(nil)`
and never told otherwise. The interactor was started in one place only: `drawRect:`.

Everything that renders outside `drawRect:` therefore rendered through a render
window that did not know where it was. The MPR views do exactly that - they ask a
hidden `VRView` for the volume and for the blended volume - and it showed:
opening a 3D MPR computed a resolution of zero fifty-eight times, which is
`aRenderer->DisplayToWorld()` answering before the renderer has a viewport, and
the code noticed and only logged it. After the preparation was extracted and
called from those paths, the same open reports it none.

Two things are asserted here that cost a leak to learn. VTK keeps the view and
the window in an `NSMutableDictionary`, which retains them, and `prepareForRelease`
empties it at teardown so the view can be deallocated; handing the view back when
it has no window - which is exactly when `viewDidMoveToWindow` fires at teardown -
kept every one of them alive. A window that closed stopped deallocating its ten
volume views entirely, and only counting them showed it.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
failures = []


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


view = strip((root / 'Horos/Sources/VTKView.mm').read_bytes().decode('latin1'))
header = (root / 'Horos/Sources/VTKView.h').read_bytes().decode('latin1')
volume = strip((root / 'Horos/Sources/VRView.mm').read_bytes().decode('latin1'))

if '- (BOOL)prepareRenderWindow;' not in header:
    failures.append('VTKView does not offer the preparation to its subclasses, so the render '
                    'paths outside drawRect: cannot ask for it')

at = view.find('- (BOOL)prepareRenderWindow')
body = view[at:view.index('\n}', at) + 2] if at >= 0 else ''
if not body:
    failures.append('prepareRenderWindow is gone')
else:
    if 'GetInitialized' not in body or 'Initialize()' not in body:
        failures.append('prepareRenderWindow does not start the interactor, which was the only '
                        'thing drawRect: did that the other render paths needed')
    if 'SetRootWindow' not in body:
        failures.append('prepareRenderWindow never points the render window at the window the '
                        'view is in, so it keeps the nil it was given during the nib load')
    windowless = body[body.find('window == nil'):]
    windowless = windowless[:windowless.find('return NO;') + 10] if 'return NO;' in windowless else ''
    if not windowless:
        failures.append('prepareRenderWindow does not answer NO when the view is in no window, so '
                        'a caller cannot tell that there is nothing to render into')
    else:
        if 'SetWindowId' in windowless:
            failures.append('the view is handed back to the render window while it is in no '
                            'window. VTK retains it in a dictionary that prepareForRelease has '
                            'just emptied, so the view is never deallocated')
        if 'SetRootWindow(NULL)' not in windowless.replace(' ', ''):
            failures.append('the window is not let go of when the view leaves it')

# The one place that used to start the interactor now asks for the preparation,
# and so does the moment the view enters or leaves a window.
for where, why in (('- (void)drawRect:', 'drawRect: no longer prepares the render window'),
                   ('- (void)viewDidMoveToWindow', 'nothing follows the view between windows')):
    at = view.find(where)
    if at < 0:
        failures.append('%s is gone' % where.strip('- (void)'))
        continue
    if 'prepareRenderWindow' not in view[at:view.index('\n}', at)]:
        failures.append(why)
if 'theRenWinInt->Initialize()' in view[view.find('- (void)drawRect:'):view.find('- (BOOL)prepareRenderWindow')]:
    failures.append('drawRect: still starts the interactor itself, so the two places can drift')

# And the render paths that never go through drawRect: stop rather than draw.
for method in ('- (void) render', '- (void) renderBlendedVolume'):
    at = volume.find(method + '\n')
    body = volume[at:volume.index('\n}', at) + 2] if at >= 0 else ''
    if not body:
        failures.append('%s is gone from VRView' % method.strip('- (void) '))
        continue
    guard = body[:body.find('_cocoaRenderWindow')]
    if 'prepareRenderWindow' not in guard:
        failures.append('%s touches the render window before asking whether there is one'
                        % method.strip('- (void) '))
    if 'return' not in guard:
        failures.append('%s asks and then renders anyway' % method.strip('- (void) '))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the render window is prepared where it is used, idempotently, and let go of when the '
      'view has no window')
