#!/usr/bin/env python3
"""Measure a rendered text label in a window capture, so a backing-scale change
can be compared against the same label before it.

The viewer draws its ROI labels and annotations as light text over the dark
image, so the ink is separable by luminance alone. What matters for the
annotation matrix is not the exact pixels but three derived quantities:

  * the ink bounding box, which says whether the label grew with the scale;
  * the glyph runs, which say whether a character was dropped or cut in half;
  * the margin between the ink and the region edge, which says the label was
    measured whole and not merely cropped by the region given here.

Comparing a 1x capture with a 2x capture of the same label then distinguishes
"the label was rebuilt for the new scale" from "the old texture was stretched"
and from "half the characters are missing".

    python3 tools/measure-label-glyphs.py shot.png --region 100,200,400,60 --json out.json
    python3 tools/measure-label-glyphs.py shot2x.png --region 200,400,800,120 \
        --compare out.json --expect-ratio 2

Needs Pillow and NumPy; exits 2 without them, like the other checkers here.
Captures contain patient text drawn in the window: do not commit them.
"""
import argparse
import json
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment guard
    print('measure-label-glyphs needs Pillow and NumPy: %s' % exc, file=sys.stderr)
    raise SystemExit(2)


def ink_mask(image, threshold, rule='luminance'):
    if rule == 'luminance':
        grey = np.asarray(image.convert('L'), dtype=np.float32) / 255.0
        return grey >= threshold
    # ROI labels are drawn in the ROI's own colour over the image, so luminance
    # alone cannot separate yellow text from a bright part of the image or from
    # the green reference lines. "warm" asks for a pixel whose blue channel is
    # clearly below the other two, which yellow satisfies and grey never does.
    rgb = np.asarray(image.convert('RGB'), dtype=np.float32) / 255.0
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    return (red >= threshold) & (green >= threshold) & \
           (blue <= red - 0.2) & (blue <= green - 0.2)


def runs(columns):
    """Start/end of each maximal stretch of columns that carry ink."""
    out, start = [], None
    for index, filled in enumerate(columns):
        if filled and start is None:
            start = index
        elif not filled and start is not None:
            out.append((start, index - 1))
            start = None
    if start is not None:
        out.append((start, len(columns) - 1))
    return out


def measure(path, region, threshold, min_gap, line=None, rule='luminance'):
    image = Image.open(path)
    if region:
        x, y, w, h = region
        if x < 0 or y < 0 or x + w > image.width or y + h > image.height:
            raise SystemExit('region %s falls outside %dx%d' % (region, image.width, image.height))
        image = image.crop((x, y, x + w, y + h))
    mask = ink_mask(image, threshold, rule)
    if not mask.any():
        return {'path': str(path), 'region': region, 'ink': False}
    lines = runs(mask.any(axis=1))
    if line is not None:
        # Rows of text are separated by blank rows, and that separation scales
        # with the text, so selecting the Nth line needs no pixel coordinates
        # and gives the same line at 1x and at 2x.
        if line >= len(lines):
            raise SystemExit('the region holds %d line(s) of ink, not line %d'
                             % (len(lines), line))
        top, bottom = lines[line]
        mask = mask[top:bottom + 1, :]
        image = image.crop((0, top, image.width, bottom + 1))
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    column_runs = runs(mask.any(axis=0))
    # Kerning leaves one empty column inside some glyphs; only a gap wider than
    # min_gap separates two glyphs.
    merged = []
    for run in column_runs:
        if merged and run[0] - merged[-1][1] - 1 < min_gap:
            merged[-1] = (merged[-1][0], run[1])
        else:
            merged.append(run)
    return {
        'path': str(path),
        'region': region,
        'rule': rule,
        'line': line,
        'lines_in_region': len(lines),
        'ink': True,
        'box': {'x': int(cols[0]), 'y': int(rows[0]),
                'width': int(cols[-1] - cols[0] + 1), 'height': int(rows[-1] - rows[0] + 1)},
        'margin': {'left': int(cols[0]), 'top': int(rows[0]),
                   'right': int(mask.shape[1] - 1 - cols[-1]),
                   'bottom': int(mask.shape[0] - 1 - rows[-1])},
        'glyph_runs': len(merged),
        'run_widths': [int(b - a + 1) for a, b in merged],
        'ink_pixels': int(mask.sum()),
    }


def compare(now, before, ratio, tolerance):
    problems = []
    if not now.get('ink') or not before.get('ink'):
        return ['one of the captures has no ink to compare']
    for key in ('width', 'height'):
        expected = before['box'][key] * ratio
        got = now['box'][key]
        if expected == 0 or abs(got - expected) / expected > tolerance:
            problems.append('%s %d, expected about %.1f at ratio %g'
                            % (key, got, expected, ratio))
    # Ink area and glyph runs only compare between captures at the SAME scale.
    #
    # Ink is counted by thresholding, and text is drawn antialiased: at 1x a
    # large share of every glyph is partial coverage that falls under the
    # threshold, while at 2x the strokes are wide enough to be fully covered.
    # Measured on this viewer's yellow ROI label, the box doubled exactly
    # (2.00 and 2.00) while the ink grew about five-fold, not four. So an
    # ink-area rule across scales would fail a correct render. Glyph runs are
    # separated by counting blank columns, and those gaps widen with the text,
    # so two neighbouring glyphs can separate at 2x that merged at 1x.
    #
    # The box dimensions carry the across-scale check on their own: characters
    # cut away shorten the box, which is case R251.
    if ratio == 1:
        expected_ink = before['ink_pixels']
        if expected_ink and abs(now['ink_pixels'] - expected_ink) / expected_ink > tolerance:
            problems.append('ink %d pixels, expected about %.0f at the same scale'
                            % (now['ink_pixels'], expected_ink))
        if now['glyph_runs'] != before['glyph_runs']:
            problems.append('glyph runs %d, expected %d: a character was dropped, merged or cut'
                            % (now['glyph_runs'], before['glyph_runs']))
    # Ink touching the region edge means the label was cropped by the region,
    # so neither the box nor the run count can be trusted as a whole label.
    # A selected line is cropped to its own rows on purpose, so only its sides
    # can say anything.
    sides = ('left', 'right') if now.get('line') is not None else now['margin'].keys()
    for side in sides:
        if now['margin'][side] == 0:
            problems.append('ink touches the %s edge of the region' % side)
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('capture')
    parser.add_argument('--region', help='x,y,width,height in image pixels')
    parser.add_argument('--threshold', type=float, default=0.65,
                        help='luminance at or above which a pixel counts as ink (default 0.65)')
    parser.add_argument('--min-gap', type=int, default=2,
                        help='empty columns that separate two glyphs (default 2)')
    parser.add_argument('--ink-rule', choices=('luminance', 'warm'), default='luminance',
                        help="how a pixel counts as ink: 'luminance' for light text on a "
                             "dark background, 'warm' for text whose blue channel is well "
                             "below its red and green, such as a yellow ROI label")
    parser.add_argument('--line', type=int,
                        help='measure only this line of text inside the region, '
                             'counting from 0 at the top; lines are found from the '
                             'blank rows between them, so the same --line picks the '
                             'same text at any scale')
    parser.add_argument('--json', help='write the measurement to this file')
    parser.add_argument('--compare', help='an earlier --json measurement to compare against')
    parser.add_argument('--expect-ratio', type=float, default=1.0,
                        help='size of this capture relative to the compared one')
    parser.add_argument('--tolerance', type=float, default=0.08,
                        help='allowed relative difference from the expected size')
    args = parser.parse_args()

    region = None
    if args.region:
        parts = args.region.split(',')
        if len(parts) != 4:
            raise SystemExit('--region wants x,y,width,height')
        region = [int(p) for p in parts]

    result = measure(args.capture, region, args.threshold, args.min_gap, args.line, args.ink_rule)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.json:
        with open(args.json, 'w') as handle:
            json.dump(result, handle, indent=2, sort_keys=True)

    if args.compare:
        with open(args.compare) as handle:
            before = json.load(handle)
        problems = compare(result, before, args.expect_ratio, args.tolerance)
        for problem in problems:
            print('FAIL:', problem, file=sys.stderr)
        if problems:
            raise SystemExit(1)
        print('PASS: label matches %s at ratio %g' % (args.compare, args.expect_ratio))


if __name__ == '__main__':
    main()
