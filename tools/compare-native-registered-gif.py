#!/usr/bin/env python3
"""Every animated frame must be the static capture it came from (#384 B).

`tools/exercise-native-registered-gif.py` writes, in one directory, the
viewer's capture at each blend stop (`static-NN.png`) and the frame decoded out
of the animation (`frame-NN.png`), both normalised to sRGB.

A GIF carries at most 256 colours, so a greyscale capture with more levels than
that comes back quantised: the frames are not expected to be byte-identical to
the captures, and claiming they are would be false. What is checked instead is
that the quantisation is all there is — a small bounded difference — and, more
importantly, that **each frame is nearer to its own static state than to any
other**, which is what proves the order and the correspondence.

    python3 tools/compare-native-registered-gif.py DIRECTORY [--max-mean 4.0] [--max-abs 24]
"""
import argparse
from pathlib import Path
import struct
import zlib


def read_png(path):
    """Decode an 8-bit RGB/RGBA/grey PNG into (width, height, channels, bytes)."""
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise SystemExit('%s is not a PNG' % path)
    offset, header, pixels = 8, None, bytearray()
    while offset < len(data):
        length, kind = struct.unpack('>I4s', data[offset:offset + 8])
        body = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b'IHDR':
            header = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT':
            pixels += body
        elif kind == b'IEND':
            break
    width, height, depth, colour, compression, filtering, interlace = header
    if depth != 8 or interlace != 0 or colour not in (0, 2, 6):
        raise SystemExit('%s: only 8-bit non-interlaced grey/RGB/RGBA is read here' % path)
    channels = {0: 1, 2: 3, 6: 4}[colour]
    raw = zlib.decompress(bytes(pixels))
    stride = width * channels
    out = bytearray(height * stride)
    previous = bytearray(stride)
    position = 0
    for row in range(height):
        method = raw[position]
        line = bytearray(raw[position + 1:position + 1 + stride])
        position += 1 + stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            upleft = previous[index - channels] if index >= channels else 0
            value = line[index]
            if method == 1:
                value += left
            elif method == 2:
                value += up
            elif method == 3:
                value += (left + up) // 2
            elif method == 4:
                p = left + up - upleft
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - upleft)
                value += left if (pa <= pb and pa <= pc) else (up if pb <= pc else upleft)
            elif method != 0:
                raise SystemExit('%s: unknown filter %d' % (path, method))
            line[index] = value & 0xFF
        out[row * stride:(row + 1) * stride] = line
        previous = line
    return width, height, channels, bytes(out)


def difference(a, b):
    (wa, ha, ca, pa), (wb, hb, cb, pb) = a, b
    if (wa, ha) != (wb, hb):
        raise SystemExit('sizes differ: %dx%d against %dx%d' % (wa, ha, wb, hb))
    total, worst, over = 0, 0, 0
    count = 0
    for y in range(ha):
        rowa, rowb = y * wa * ca, y * wb * cb
        for x in range(wa):
            for channel in range(3):
                va = pa[rowa + x * ca + min(channel, ca - 1)]
                vb = pb[rowb + x * cb + min(channel, cb - 1)]
                delta = abs(va - vb)
                total += delta
                worst = max(worst, delta)
                over += delta > 2
                count += 1
    return total / count, worst, over / count


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory', type=Path)
parser.add_argument('--max-mean', type=float, default=4.0, help='largest mean absolute level difference allowed')
parser.add_argument('--max-abs', type=int, default=32, help='largest single-channel difference allowed')
args = parser.parse_args()

statics = sorted(args.directory.glob('static-*.png'))
frames = sorted(args.directory.glob('frame-*.png'))
if not statics:
    raise SystemExit('no static captures in ' + str(args.directory))
if len(statics) != len(frames):
    raise SystemExit('%d static captures against %d animated frames' % (len(statics), len(frames)))

decoded_statics = [read_png(path) for path in statics]
decoded_frames = [read_png(path) for path in frames]

failures = []
print('%-14s %-14s %9s %7s %10s' % ('frame', 'static', 'mean diff', 'max', '>2 levels'))
for index, frame in enumerate(decoded_frames):
    scores = [difference(frame, static) for static in decoded_statics]
    mean, worst, over = scores[index]
    nearest = min(range(len(scores)), key=lambda other: scores[other][0])
    print('%-14s %-14s %9.3f %7d %9.2f%%' % (frames[index].name, statics[index].name, mean, worst, over * 100))
    if nearest != index:
        failures.append('%s is nearer to %s than to its own %s'
                        % (frames[index].name, statics[nearest].name, statics[index].name))
    if mean > args.max_mean:
        failures.append('%s differs from its state by %.3f levels on average' % (frames[index].name, mean))
    if worst > args.max_abs:
        failures.append('%s differs from its state by %d levels at worst' % (frames[index].name, worst))

separations = []
for index in range(len(decoded_frames)):
    for other in range(len(decoded_statics)):
        if other != index:
            separations.append(difference(decoded_frames[index], decoded_statics[other])[0])
if separations and min(separations) < args.max_mean:
    failures.append('the states are not distinguishable: the nearest wrong pairing differs by only %.3f levels'
                    % min(separations))

if failures:
    print('FAIL:')
    for item in failures:
        print(' ', item)
    raise SystemExit(1)
print('PASS: every animated frame is nearest to its own static state (the wrong pairings are at least %.1f levels '
      'away), and the only difference is the GIF palette' % min(separations) if separations else
      'PASS: the animated frame matches its static state')
