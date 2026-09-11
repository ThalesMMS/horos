#!/usr/bin/env python3
"""Read back the colour a ROI was actually drawn in, from a window capture.

The image under a ROI is greyscale, so every pixel the ROI painted is a pixel
whose channels disagree. That separates the ROI's own ink from the image
without knowing where the ROI is, and without assuming which colour was asked
for - which is the point, since the question is whether the colour on screen
matches the one that was chosen.

Reports the mean and the strongest ink pixel, the hue order of the channels,
and the saturation. Comparing two captures then answers both halves of the
case: whether the hue follows the selection, and whether lowering the opacity
actually blends the ink further towards the image instead of doing nothing.

    python3 tools/measure-roi-ink-colour.py shot.png --region 200,60,200,60
    python3 tools/measure-roi-ink-colour.py shot.png --expect-hue R=G>B

Needs Pillow and NumPy; exits 2 without them. Captures hold the patient text
drawn in the window: do not commit them.
"""
import argparse
import json
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment guard
    print('measure-roi-ink-colour needs Pillow and NumPy: %s' % exc, file=sys.stderr)
    raise SystemExit(2)


def hue_order(rgb, tolerance):
    """Describe the channel order, e.g. 'R=G>B' for yellow, 'B>R=G' for blue."""
    names = ['R', 'G', 'B']
    order = sorted(range(3), key=lambda i: -rgb[i])
    out = names[order[0]]
    for previous, current in zip(order, order[1:]):
        out += '=' if abs(rgb[previous] - rgb[current]) <= tolerance else '>'
        out += names[current]
    return out


def measure(path, region, separation, tolerance):
    image = Image.open(path)
    if region:
        x, y, w, h = region
        image = image.crop((x, y, x + w, y + h))
    rgb = np.asarray(image.convert('RGB'), dtype=np.int16)
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    ink = spread >= separation
    if not ink.any():
        return {'path': str(path), 'region': region, 'ink': False}
    pixels = rgb[ink]
    strongest = pixels[np.argmax(spread[ink])]
    mean = pixels.mean(axis=0)
    return {
        'path': str(path),
        'region': region,
        'ink': True,
        'ink_pixels': int(ink.sum()),
        'mean': [round(float(c), 1) for c in mean],
        'strongest': [int(c) for c in strongest],
        'hue_order': hue_order(strongest, tolerance),
        'mean_hue_order': hue_order(mean, tolerance),
        'max_separation': int(spread[ink].max()),
        'mean_separation': round(float(spread[ink].mean()), 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('capture')
    parser.add_argument('--region', help='x,y,width,height in image pixels')
    parser.add_argument('--separation', type=int, default=40,
                        help='how far the channels must disagree for a pixel to count as '
                             'ROI ink over a greyscale image (default 40)')
    parser.add_argument('--tolerance', type=int, default=24,
                        help='channels within this are called equal in the hue order')
    parser.add_argument('--expect-hue', help="require this hue order, e.g. 'R=G>B'")
    parser.add_argument('--json', help='write the measurement to this file')
    args = parser.parse_args()

    region = None
    if args.region:
        parts = args.region.split(',')
        if len(parts) != 4:
            raise SystemExit('--region wants x,y,width,height')
        region = [int(p) for p in parts]

    result = measure(args.capture, region, args.separation, args.tolerance)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.json:
        with open(args.json, 'w') as handle:
            json.dump(result, handle, indent=2, sort_keys=True)

    if args.expect_hue:
        if not result.get('ink'):
            print('FAIL: no ROI ink found to check the hue of', file=sys.stderr)
            raise SystemExit(1)
        if result['hue_order'] != args.expect_hue:
            print('FAIL: hue order %s, expected %s (strongest pixel %s)'
                  % (result['hue_order'], args.expect_hue, result['strongest']), file=sys.stderr)
            raise SystemExit(1)
        print('PASS: the ink is %s' % args.expect_hue)


if __name__ == '__main__':
    main()
