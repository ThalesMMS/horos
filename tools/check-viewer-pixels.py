#!/usr/bin/env python3
"""Measure what a 2D viewer is actually presenting, from outside the process.

Reports of an invisible viewer - a window that is there, with thumbnails beside
it, and no picture in it - were argued over with screen captures on one side and
`glReadPixels` on the other. A capture can be black while the framebuffer holds
the image; a framebuffer read synchronises the GPU and a debugger changes the
timing, so neither settles it alone. This takes the compositor's own output,
with no debugger attached, and asks whether the picture is there.

It captures one window - not the screen - drops the title bar and the annotation
margins, and measures the rest:

    python3 tools/check-viewer-pixels.py --window <CGWindowID> [--inset 150] [--trim]
        [--expect ramp-right --expect bright-corner] [--save out.png]

Capture one window, never the display: `screencapture -l` takes the window alone,
so nothing else the person is doing is recorded. `--rect X,Y,W,H` measures part of
a capture given with `--capture`, in screen points and top-left origin; `--ignore`
blanks a floating panel that overlaps it, and `--scale 2` is for a Retina capture,
which is in backing pixels while the rectangle is in points.

`--expect anything`, the default, answers the weak question the reports raise: is
anything drawn at all? A viewport carrying one value fails it.

The others check the picture against the fixture from
`tools/generate-window-and-scale-fixture.py`, a ramp brightening to the right with
a bright square in its top-left corner. `ramp-right` requires the column means to
rise almost everywhere, left to right - a flipped picture, stale memory or the
wrong series fails. `bright-corner` requires that corner to be brighter than what
follows it, and needs an inset small enough to keep it.

Exit 0 when the picture is there, 1 when it is not, 2 when Pillow and NumPy are
missing. A capture still holds patient text drawn in the window: keep it out of
commits.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy
    from PIL import Image
except ImportError as missing:
    print('skipped: needs Pillow and NumPy to measure the capture (%s)' % missing)
    sys.exit(2)

SCREENCAPTURE = '/usr/sbin/screencapture'


def rectangle(text):
    parts = [int(round(float(p))) for p in text.split(',')]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError('expected X,Y,W,H, got %r' % text)
    return parts


parser = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--window', type=int,
                    help='CGWindowID to capture on its own; the whole window is measured')
parser.add_argument('--rect', type=rectangle,
                    help='rectangle to measure in screen points, top-left origin; needed when '
                         'measuring a capture of the whole screen')
parser.add_argument('--ignore', type=rectangle, action='append', default=[],
                    help='a rectangle to blank before measuring; repeatable')
parser.add_argument('--inset', type=int, default=96,
                    help='points to drop from each edge of the window, to clear the title bar '
                         'and the annotation margins (default 96)')
parser.add_argument('--expect', action='append', default=[],
                    choices=('anything', 'ramp-right', 'bright-corner'),
                    help='repeatable; defaults to anything')
parser.add_argument('--trim', nargs='?', type=int, const=0, default=None, metavar='GREY',
                    help='after the inset, drop the leading and trailing rows and columns in '
                         'which fewer than one pixel in a hundred is brighter than GREY (0 by '
                         'default) - the letterbox a viewer draws around a picture that is not '
                         'the shape of its window')
parser.add_argument('--scale', type=int, default=1,
                    help='backing pixels per point: 1 for a plain display, 2 for Retina. A '
                         'capture wider than the display in points means this is wrong.')
parser.add_argument('--capture', type=Path, help='measure this PNG instead of capturing')
parser.add_argument('--save', type=Path, help='write the measured crop here')
arguments = parser.parse_args()
expectations = set(arguments.expect) or {'anything'}
if not arguments.window and not arguments.rect:
    parser.error('give --window, or --rect with the capture to measure')

if arguments.capture:
    shot = arguments.capture
    temporary = None
else:
    if not Path(SCREENCAPTURE).exists():
        raise SystemExit('%s is not available' % SCREENCAPTURE)
    temporary = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    temporary.close()
    shot = Path(temporary.name)
    command = [SCREENCAPTURE, '-x', '-o']
    if arguments.window:
        command += ['-l', str(arguments.window)]
    if subprocess.run(command + [str(shot)]).returncode or not shot.stat().st_size:
        Path(temporary.name).unlink(missing_ok=True)
        raise SystemExit('nothing was captured. A window id goes stale as soon as the window '
                         'closes or the application restarts - ask for the list again%s.'
                         % ('' if arguments.window else ', or check screen recording permission'))

try:
    screen = Image.open(shot).convert('L')
    factor = arguments.scale
    x, y, width, height = arguments.rect or (0, 0, screen.width // factor, screen.height // factor)
    picture = numpy.asarray(screen, dtype=numpy.int16)
    for hidden in arguments.ignore:
        hx, hy, hw, hh = [v * factor for v in hidden]
        picture[max(hy, 0):hy + hh, max(hx, 0):hx + hw] = -1
    x, y, width, height = [v * factor for v in (x, y, width, height)]
    inset = arguments.inset * factor
    crop = picture[y + inset:y + height - inset, x + inset:x + width - inset]
finally:
    if temporary:
        Path(temporary.name).unlink(missing_ok=True)

if crop.size == 0:
    raise SystemExit('the rectangle and the inset leave nothing to measure')

if arguments.trim is not None:
    # A hairline drawn across the whole window - a ruler, a border - would keep
    # every column "lit" if one pixel were enough, so ask for a hundredth of one.
    above = numpy.ma.filled(numpy.ma.masked_less(crop, 0) > arguments.trim, False)
    litColumns = numpy.flatnonzero(above.mean(axis=0) > 0.01)
    litRows = numpy.flatnonzero(above.mean(axis=1) > 0.01)
    if litColumns.size and litRows.size:
        crop = crop[litRows[0]:litRows[-1] + 1, litColumns[0]:litColumns[-1] + 1]
        print('%-22s %d x %d after dropping the black border'
              % ('picture', crop.shape[1] // factor, crop.shape[0] // factor))
    if crop.size == 0:
        raise SystemExit('nothing but black inside the measured rectangle')
if arguments.save:
    Image.fromarray(numpy.clip(crop, 0, 255).astype('uint8')).save(arguments.save)

visible = crop[crop >= 0]
if visible.size == 0:
    raise SystemExit('every measured pixel was covered by an --ignore rectangle')

greys = numpy.unique(visible)
black = float((visible == 0).sum()) / visible.size
print('%-22s %d x %d points, %d sampled' % ('measured area', crop.shape[1] // factor,
                                            crop.shape[0] // factor, visible.size))
print('%-22s %d..%d, mean %.1f' % ('grey', visible.min(), visible.max(), visible.mean()))
print('%-22s %d' % ('distinct greys', len(greys)))
print('%-22s %.1f%%' % ('pure black', 100.0 * black))

failures = []
if len(greys) < 8:
    failures.append('the viewport carries %d distinct grey%s: nothing is being drawn in it'
                    % (len(greys), '' if len(greys) == 1 else 's'))

if 'ramp-right' in expectations:
    columns = numpy.ma.masked_less(crop, 0).mean(axis=0)
    columns = numpy.ma.filled(columns, numpy.nan)
    usable = columns[~numpy.isnan(columns)]
    rising = float((numpy.diff(usable) >= 0).sum()) / max(len(usable) - 1, 1)
    print('%-22s %.1f%% of adjacent columns' % ('brightens rightwards', 100.0 * rising))
    if rising < 0.9:
        failures.append('the picture does not brighten to the right: only %.1f%% of adjacent '
                        'columns rise, where the fixture is a ramp' % (100.0 * rising))
if 'bright-corner' in expectations:
    side = max(min(crop.shape) // 6, 4)
    corner = numpy.ma.masked_less(crop[:side, :side], 0).mean()
    beside = numpy.ma.masked_less(crop[:side, side:2 * side], 0).mean()
    print('%-22s %.1f against %.1f beside it' % ('bright corner', corner, beside))
    if not corner > beside:
        failures.append('the bright corner of the fixture is not brighter than what follows it')

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: the viewer is presenting a picture')
