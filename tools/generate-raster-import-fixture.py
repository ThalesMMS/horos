#!/usr/bin/env python3
"""Raster images with a picture that cannot survive being read wrongly.

A converter that swaps width for height, gets the row stride wrong, flips the
rows or reorders the channels produces something that still looks like an image.
So the picture here is deliberately asymmetric in every one of those ways:

  * 64 wide by 48 high, so a swap is a different shape
  * a 6x6 white square in the top-left corner only, so a vertical flip moves it
  * red rising left to right, green rising top to bottom, blue constant 64, so a
    channel swap changes which way the gradient runs
  * a single black column at x = 61, so a stride that is one pixel out smears

Written with ffmpeg from raw RGB, in the formats the application says it reads
natively. JPEG is lossy and is compared with tolerance; the others are exact.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination', type=Path, help='an empty directory for the files')
parser.add_argument('--width', type=int, default=64)
parser.add_argument('--height', type=int, default=48)
arguments = parser.parse_args()

arguments.destination.mkdir(parents=True, exist_ok=True)
if any(arguments.destination.iterdir()):
    raise SystemExit('%s is not empty' % arguments.destination)

width, height = arguments.width, arguments.height
BLUE = 64

columns = numpy.arange(width)
rows = numpy.arange(height)
red = numpy.tile((columns * 255 // max(width - 1, 1)).astype(numpy.uint8), (height, 1))
green = numpy.tile((rows * 255 // max(height - 1, 1)).astype(numpy.uint8)[:, None], (1, width))
blue = numpy.full((height, width), BLUE, dtype=numpy.uint8)
picture = numpy.stack([red, green, blue], axis=-1)
picture[:6, :6] = [255, 255, 255]        # the corner that says which way is up
picture[:, 61] = [0, 0, 0]               # the column that says the stride is right

raw = arguments.destination / 'source.rgb'
raw.write_bytes(picture.tobytes())

FORMATS = [
    ('png', [], True),
    ('tiff', [], True),
    ('bmp', [], True),
    ('gif', [], False),          # 256 colours, so not exact
    ('jpg', ['-q:v', '2'], False),
]

made = []
for extension, options, exact in FORMATS:
    path = arguments.destination / ('raster.%s' % extension)
    command = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', '%dx%d' % (width, height), '-i', str(raw)] + options + [str(path)]
    if subprocess.run(command, capture_output=True).returncode != 0:
        print('%-14s could not be written' % extension)
        continue
    made.append({'name': path.name, 'format': extension, 'exact': exact,
                 'width': width, 'height': height})
    print('%-14s %6d bytes  %s' % (extension, path.stat().st_size,
                                   'exact' if exact else 'approximate'))

raw.unlink()

# A one-page PDF wrapping the JPEG, written by hand so that nothing has to be
# installed to make it. An importer that accepts PDF has to get past the document
# structure to the image inside; one that does not has to say so rather than
# pretend.
jpeg = arguments.destination / 'raster.jpg'
if jpeg.exists():
    image = jpeg.read_bytes()
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /XObject '
        b'<< /Im0 4 0 R >> >> /Contents 5 0 R >>' % (width, height),
        b'<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB '
        b'/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n' % (width, height, len(image))
        + image + b'\nendstream',
        None,
    ]
    stream = b'q %d 0 0 %d 0 0 cm /Im0 Do Q' % (width, height)
    objects[4] = b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream'

    document = bytearray(b'%PDF-1.4\n')
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(document))
        document += b'%d 0 obj\n' % number + content + b'\nendobj\n'
    start = len(document)
    document += b'xref\n0 %d\n' % (len(objects) + 1)
    document += b'0000000000 65535 f \n'
    for offset in offsets:
        document += b'%010d 00000 n \n' % offset
    document += (b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'
                 % (len(objects) + 1, start))
    path = arguments.destination / 'raster.pdf'
    path.write_bytes(bytes(document))
    made.append({'name': path.name, 'format': 'pdf', 'exact': False,
                 'width': width, 'height': height})
    print('%-14s %6d bytes  %s' % ('pdf', path.stat().st_size, 'approximate (wraps the JPEG)'))

(arguments.destination / 'expected.json').write_text(json.dumps(
    {'width': width, 'height': height, 'blue': BLUE, 'files': made}, indent=1))
print()
print('%d file(s) in %s' % (len(made), arguments.destination))
sys.exit(0 if made else 1)
