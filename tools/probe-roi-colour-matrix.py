#!/usr/bin/env python3
"""Measure what the 2D viewer actually paints for a ROI's colour and opacity.

Case R254 of the annotation matrix asks two things a preference value cannot
answer: whether the colour on screen is the one that was chosen, and whether
lowering the opacity really blends the ink further towards the image. Both are
answered by drawing known colours over a known background and reading the
pixels back.

The scene is built in the running development application through lldb: four
rectangle ROIs side by side, red, green, blue and yellow, over the greyscale
gradient of the open series. `--setup` creates them and scales the image to
fit; `--opacity` then sets one opacity on all four and captures the viewer
window. Inside a horizontal band that crosses the four rectangles and misses
their text, each hue's strongest pixel is reported together with the local
background, which is what the blend arithmetic needs:

    painted = chosen * opacity + background * (1 - opacity)

    python3 tools/probe-roi-colour-matrix.py --setup
    python3 tools/probe-roi-colour-matrix.py --opacity 1.0 --opacity 0.5

Needs the isolated development build running and signed for debugging; see
docs/native-validation-harness.md. Captures hold the window's patient text:
keep them out of commits.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment guard
    print('probe-roi-colour-matrix needs Pillow and NumPy: %s' % exc, file=sys.stderr)
    raise SystemExit(2)

EXECUTABLE = 'HorosDevelopment.app/Contents/MacOS/Horos'
# Message sends go through typed function pointers: lldb has no declarations for
# these classes, and an untyped receiver passes a double where a float is
# expected, which lands as garbage.
VIEWER = ('expr -l objc++ -- id $vc = ((id(*)(id,SEL))objc_msgSend)'
          '((id)NSClassFromString(@"ViewerController"), @selector(frontMostDisplayed2DViewer))\n'
          'expr -l objc++ -- id $iv = ((id(*)(id,SEL))objc_msgSend)($vc, @selector(imageView))\n'
          'expr -l objc++ -- long $cur = ((long(*)(id,SEL))objc_msgSend)($iv, @selector(curImage))\n'
          'expr -l objc++ -- id $slice = ((id(*)(id,SEL,unsigned long))objc_msgSend)('
          '((id(*)(id,SEL))objc_msgSend)($vc, @selector(roiList)), @selector(objectAtIndex:), '
          '(unsigned long)$cur)\n')
COLOURS = [('red', 1, 0, 0), ('green', 0, 1, 0), ('blue', 0, 0, 1), ('yellow', 1, 1, 0)]
TOOL_RECTANGLE = 6   # ToolMode tROI, DCMView.h
ANNOTATION_GRAPHICS = 1   # annotGraphics: keep the overlays out of the measurement


def horosProcess():
    listing = subprocess.run(['/bin/ps', '-axo', 'pid=,command='], capture_output=True, text=True).stdout
    for line in listing.splitlines():
        pid, _, command = line.strip().partition(' ')
        if EXECUTABLE in command:
            return int(pid)
    print('no isolated development build is running (%s)' % EXECUTABLE, file=sys.stderr)
    raise SystemExit(2)


def lldb(pid, script):
    with tempfile.NamedTemporaryFile('w', suffix='.lldb', delete=False) as handle:
        handle.write('thread select 1\n' + VIEWER + script + 'detach\nquit\n')
        name = handle.name
    result = subprocess.run(['lldb', '-p', str(pid), '-b', '-s', name],
                            capture_output=True, text=True)
    Path(name).unlink()
    if 'error:' in result.stdout:
        print(result.stdout, file=sys.stderr)
        raise SystemExit('lldb refused the expression')
    return result.stdout


def value(output, kind):
    found = re.findall(r'^\(%s\) \$\d+ = (.+)$' % re.escape(kind), output, re.M)
    return found


def setup(pid):
    script = ['expr -l objc++ -- (void)[[NSUserDefaults standardUserDefaults] setInteger:%d forKey:@"ANNOTATIONS"]\n'
              % ANNOTATION_GRAPHICS,
              'expr -l objc++ -- (void)[$slice removeAllObjects]\n']
    # Four upright rectangles across a 32 pixel wide image, clear of each other.
    for index, (name, r, g, b) in enumerate(COLOURS):
        # A persistent lldb variable cannot be redefined, so each ROI gets its own.
        script.append(
            'expr -l objc++ -- id $r%d = ((id(*)(id,SEL,short))objc_msgSend)($vc, @selector(newROI:), (short)%d)\n'
            'expr -l objc++ -- ((void(*)(id,SEL,CGRect))objc_msgSend)($r%d, @selector(setROIRect:), CGRectMake(%d,4,6,24))\n'
            'expr -l objc++ -- ((void(*)(id,SEL,id))objc_msgSend)($r%d, @selector(setName:), @"R254-%s")\n'
            'expr -l objc++ -- ((void(*)(id,SEL,id,signed char))objc_msgSend)($r%d, @selector(setNSColor:globally:), '
            '(id)[NSColor colorWithCalibratedRed:%d green:%d blue:%d alpha:1], (signed char)0)\n'
            'expr -l objc++ -- (void)[$slice addObject:$r%d]\n'
            % (index, TOOL_RECTANGLE, index, 1 + 8 * index, index, name, index, r, g, b, index))
    script.append('expr -l objc++ -- (void)[$iv setOriginX:0 Y:0]\n'
                  'expr -l objc++ -- (void)[$iv scaleToFit]\n'
                  'expr -l objc++ -- (void)[$iv display]\n'
                  'expr -l objc++ -- (long)[$slice count]\n')
    written = value(lldb(pid, ''.join(script)), 'long')
    return int(written[-1]) if written else 0


def applyOpacity(pid, opacity):
    script = (
        'expr -l objc++ -- for (unsigned long i = 0; i < (unsigned long)[$slice count]; i++) '
        '{ ((void(*)(id,SEL,float,signed char))objc_msgSend)((id)[$slice objectAtIndex:i], '
        '@selector(setOpacity:globally:), (float)%r, (signed char)0); }\n'
        'expr -l objc++ -- (void)[[NSNotificationCenter defaultCenter] postNotificationName:@"roiChange" '
        'object:(id)[$slice objectAtIndex:0] userInfo:nil]\n'
        'expr -l objc++ -- (void)[$iv setNeedsDisplay:YES]\n'
        'expr -l objc++ -- (void)[$iv display]\n'
        % opacity)
    # Read the value back from the object that draws, not from the request.
    script += ''.join(
        'expr -l objc++ -- (float)((float(*)(id,SEL))objc_msgSend)((id)[$slice objectAtIndex:%d], @selector(opacity))\n'
        % index for index in range(len(COLOURS)))
    return [float(v) for v in value(lldb(pid, script), 'float')]


def windowGeometry(pid):
    script = ('expr -l objc++ -- id $w = ((id(*)(id,SEL))objc_msgSend)($vc, @selector(window))\n'
              'expr -l objc++ -- (long)[$w windowNumber]\n'
              'expr -l objc++ -- (double)[$w backingScaleFactor]\n'
              'expr -l objc++ -- (double)((CGRect(*)(id,SEL))objc_msgSend)($w, @selector(frame)).size.height\n'
              'expr -l objc++ -- (double)((CGRect(*)(id,SEL))objc_msgSend)($iv, @selector(bounds)).size.height\n')
    output = lldb(pid, script)
    number = int(value(output, 'long')[-1])
    scale, windowHeight, viewHeight = (float(v) for v in value(output, 'double')[-3:])
    return number, scale, windowHeight, viewHeight


def capture(number, destination):
    subprocess.run(['screencapture', '-x', '-o', '-l%d' % number, str(destination)], check=True)


def measure(path, top, bottom):
    """Ink of each hue inside a band, with the background it was painted over."""
    image = np.asarray(Image.open(path).convert('RGB')).astype(float)[top:bottom]
    red, green, blue = image[..., 0], image[..., 1], image[..., 2]
    separation = image.max(axis=2) - image.min(axis=2)
    ink = separation >= 30
    hues = {'red': (red > green + 30) & (red > blue + 30),
            'green': (green > red + 30) & (green > blue + 30),
            'blue': (blue > red + 30) & (blue > green + 30),
            'yellow': (red > blue + 30) & (green > blue + 30) & (abs(red - green) <= 40)}
    report = {}
    for name, mask in hues.items():
        mask = mask & ink
        if not mask.any():
            report[name] = {'pixels': 0}
            continue
        peak = separation[mask].max()
        strongest = [int(image[..., c][mask & (separation == peak)][0]) for c in range(3)]
        report[name] = {'pixels': int(mask.sum()), 'peak': strongest,
                        'peak_separation': int(peak),
                        'mean': [round(float(image[..., c][mask].mean()), 1) for c in range(3)]}
    report['background_outside_ink'] = [round(float(image[..., c][~ink].mean()), 1) for c in range(3)]
    return report


def linearity(background, opaque, painted, opacity):
    """Compare a capture against the composite its opacity should produce.

    A single pass drawn at opacity a over an unchanged background gives
    `a * opaque + (1 - a) * background` at every pixel, so the two extreme
    captures predict every intermediate one without modelling the renderer.
    The ROI label is two passes, a shadow and the text, each faded on its own;
    that composite carries a term `background * (a*a - a)` which a single-pass
    prediction cannot express, so the residual is reported separately over the
    pixels with a dark background, where that term is small.
    """
    ink = np.abs(opaque - background).sum(axis=2) > 25
    if not ink.any():
        return {'painted_pixels': 0}
    predicted = opacity * opaque + (1 - opacity) * background
    error = np.abs(painted - predicted)[ink]
    dark = (background.mean(axis=2) < 40)[ink]
    report = {'painted_pixels': int(ink.sum()),
              'mean_error': round(float(error.mean()), 2),
              'p99_error': round(float(np.percentile(error, 99)), 1),
              'max_error': round(float(error.max()), 1)}
    if dark.any():
        report['dark_background_pixels'] = int(dark.sum())
        report['dark_mean_error'] = round(float(error[dark].mean()), 2)
        report['dark_p99_error'] = round(float(np.percentile(error[dark], 99)), 1)
        report['dark_p999_error'] = round(float(np.percentile(error[dark], 99.9)), 1)
        report['dark_max_error'] = round(float(error[dark].max()), 1)
    return report


def implied(peak, chosen, opacity):
    """The background each channel implies, so the blend can be checked.

    painted = chosen * opacity + background * (1 - opacity), so a consistent
    set of channels agrees on one background. Saturated ink at opacity 1 says
    nothing about the background and is reported as None.
    """
    if opacity >= 1:
        return None
    return [round((painted - 255.0 * want * opacity) / (1 - opacity), 1)
            for painted, want in zip(peak, chosen)]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--setup', action='store_true', help='create the four ROIs and scale to fit')
    parser.add_argument('--opacity', type=float, action='append', default=[],
                        help='measure at this opacity; repeatable')
    parser.add_argument('--captures', default=None,
                        help='directory for the window captures (a temporary one by default)')
    parser.add_argument('--band', default='250,450', help='top,bottom of the measured band in pixels')
    parser.add_argument('--linearity', action='store_true',
                        help='also capture at opacity 0 and 1 and check each opacity against them')
    parser.add_argument('--json', help='write the measurements to this file')
    arguments = parser.parse_args()

    pid = horosProcess()
    result = {'pid': pid}
    if arguments.setup:
        result['rois'] = setup(pid)
    number, scale, windowHeight, viewHeight = windowGeometry(pid)
    result['window'] = number
    result['backing_scale'] = scale
    top, bottom = (int(v) * int(scale) for v in arguments.band.split(','))
    directory = Path(arguments.captures) if arguments.captures else Path(tempfile.mkdtemp(prefix='horos-r254-'))
    directory.mkdir(parents=True, exist_ok=True)
    result['measurements'] = []
    extremes = {}
    if arguments.linearity:
        for edge in (0.0, 1.0):
            applyOpacity(pid, edge)
            path = directory / ('edge-%s.png' % edge)
            capture(number, path)
            extremes[edge] = np.asarray(Image.open(path).convert('RGB')).astype(float)
    for opacity in arguments.opacity:
        readBack = applyOpacity(pid, opacity)
        path = directory / ('opacity-%s.png' % opacity)
        capture(number, path)
        entry = {'requested': opacity, 'read_back': readBack, 'capture': str(path),
                 'ink': measure(path, top, bottom)}
        for name, r, g, b in COLOURS:
            hue = entry['ink'].get(name, {})
            if 'peak' in hue:
                hue['implied_background'] = implied(hue['peak'], (r, g, b), opacity)
        if extremes:
            entry['linearity'] = linearity(extremes[0.0], extremes[1.0],
                                           np.asarray(Image.open(path).convert('RGB')).astype(float),
                                           opacity)
        result['measurements'].append(entry)
    print(json.dumps(result, indent=1, sort_keys=True))
    if arguments.json:
        Path(arguments.json).write_text(json.dumps(result, indent=1, sort_keys=True))


if __name__ == '__main__':
    main()
