#!/usr/bin/env python3
"""The label measurement tool has to tell a rebuilt label from a cut one."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
tool = root / 'tools/measure-label-glyphs.py'

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    print('needs Pillow: %s' % exc, file=sys.stderr)
    raise SystemExit(2)


def font(size):
    for name in ('/System/Library/Fonts/Supplemental/Arial.ttf',
                 '/System/Library/Fonts/Helvetica.ttc',
                 '/System/Library/Fonts/Geneva.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return None


def label(path, scale, text='Length: 5.501 cm', cut=0):
    """A light label over a dark image, the way the viewer draws one."""
    face = font(12 * scale)
    if face is None:
        raise SystemExit(2)
    image = Image.new('RGB', (400 * scale, 60 * scale), (12, 12, 12))
    draw = ImageDraw.Draw(image)
    draw.text((20 * scale, 20 * scale), text, font=face, fill=(255, 255, 255))
    if cut:
        # Paint over the tail, the way a stale texture box clips the glyphs.
        box = draw.textbbox((20 * scale, 20 * scale), text, font=face)
        keep = box[0] + int((box[2] - box[0]) * (1 - cut))
        draw.rectangle([keep, box[1] - 2, box[2] + 2, box[3] + 2], fill=(12, 12, 12))
    image.save(path)


def run(args, expect_zero=True):
    done = subprocess.run([sys.executable, str(tool)] + args,
                          capture_output=True, text=True)
    if expect_zero and done.returncode != 0:
        print(done.stdout, done.stderr, file=sys.stderr)
        raise SystemExit('expected success: %s' % args)
    return done


failures = []
with tempfile.TemporaryDirectory(prefix='horos-label-measure-') as tmp:
    p = Path(tmp)
    label(p / '1x.png', 1)
    label(p / '2x.png', 2)
    label(p / '2x-cut.png', 2, cut=0.45)

    run([str(p / '1x.png'), '--json', str(p / '1x.json')])
    before = json.loads((p / '1x.json').read_text())
    if not before['ink'] or before['glyph_runs'] < 3:
        failures.append('the 1x label was not measured: %s' % before)

    # The same label on a 2x backing store is twice the pixels and the same
    # glyphs. That is the transition the annotation matrix asks about.
    run([str(p / '2x.png'), '--compare', str(p / '1x.json'), '--expect-ratio', '2'])

    # Comparing 2x against 1x without saying so must not pass, or the check
    # would accept a label that never grew.
    same = run([str(p / '2x.png'), '--compare', str(p / '1x.json')], expect_zero=False)
    if same.returncode == 0:
        failures.append('a doubled label passed as unchanged')

    # Half the characters painted out has to fail, which is case R251.
    cut = run([str(p / '2x-cut.png'), '--compare', str(p / '1x.json'),
               '--expect-ratio', '2'], expect_zero=False)
    if cut.returncode == 0:
        failures.append('a clipped label passed as whole')
    if 'glyph runs' not in cut.stderr and 'width' not in cut.stderr:
        failures.append('a clipped label did not report the glyph or width difference')

    # Ink running into the region edge means the region cropped the label, so
    # the numbers describe the crop and not the label. Cut the measured box in
    # from each side, so the ink certainly continues past every edge.
    box = before['box']
    inside = '%d,%d,%d,%d' % (box['x'] + 6, box['y'], box['width'] - 12, box['height'])
    edge = run([str(p / '1x.png'), '--region', inside], expect_zero=False)
    measured = json.loads(edge.stdout)
    # A crop boundary can land in a kerning gap, so "reaches the edge" is
    # within a pixel, not exactly zero.
    if measured['margin']['left'] > 1 or measured['margin']['right'] > 1:
        failures.append('a cropping region did not show a zero margin: %s' % measured['margin'])

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: label measurement separates a rebuilt label from a cut one')
