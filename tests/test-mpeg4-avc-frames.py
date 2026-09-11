#!/usr/bin/env python3
"""Every frame of an MPEG-4 AVC instance decodes, and is the frame it should be.

Reads the encapsulated H.264 stream out of the fixture, decodes each frame with
the same Swift decoder the viewer uses, and compares it against ffmpeg's decode
of the same stream. A frame has to be closer to its own reference than to the
frames beside it: that is what catches a decoder handing back pictures in the
order they were coded rather than the order they are shown, which is a different
sequence as soon as the stream has B pictures and which VideoToolbox does not
correct for.

The fixture and ffmpeg are not in this repository. Make one with

    python3 tools/generate-mpeg4-fixture.py <dir> [--b-frames 3]

Usage: python test-mpeg4-avc-frames.py MPEG4_FIXTURE [MPEG4_FIXTURE...]
       each being a directory holding one instance written by that generator
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if len(sys.argv) < 2:
    print('skipped: needs an MPEG-4 AVC fixture directory: MPEG4_FIXTURE', file=sys.stderr)
    raise SystemExit(2)
if shutil.which('ffmpeg') is None:
    print('skipped: needs ffmpeg to decode the reference frames: MPEG4_FIXTURE', file=sys.stderr)
    raise SystemExit(2)
try:
    import pydicom
except ImportError:
    print('skipped: needs pydicom to read the fixture: MPEG4_FIXTURE', file=sys.stderr)
    raise SystemExit(2)

root = Path(__file__).resolve().parents[1]

harness = r'''
import Foundation

// Writes each frame, in the order the frames are shown, as raw RGB.
let arguments = CommandLine.arguments
let stream = FileManager.default.contents(atPath: arguments[1])!
guard let decoder = H264StreamDecoder(annexBStream: stream) else {
    FileHandle.standardError.write(Data("the stream was refused\n".utf8))
    exit(1)
}
let out = URL(fileURLWithPath: arguments[2])
try! FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
print("\(decoder.frameCount) \(decoder.width) \(decoder.height) \(decoder.displayOrderIsFromTheStream)")

// Out of order on purpose for half of them: a viewer drags the slider, and a
// decoder that only works forwards would pass a sequential test.
var order = Array(0..<decoder.frameCount)
if arguments.count > 3, arguments[3] == "--shuffled" {
    order = order.filter { $0 % 2 == 1 }.reversed() + order.filter { $0 % 2 == 0 }
}
for index in order {
    guard let rgb = decoder.rgbFrame(at: index) else {
        FileHandle.standardError.write(Data("frame \(index) did not decode\n".utf8))
        exit(1)
    }
    try rgb.write(to: out.appendingPathComponent(String(format: "%04d.rgb", index)))
}
// Past the end is nothing, not the last frame again.
precondition(decoder.rgbFrame(at: decoder.frameCount) == nil)
precondition(decoder.rgbFrame(at: -1) == nil)
'''


def blocks(frame, width, height, side=8):
    """Mean of each side x side block, per channel.

    Whole-pixel comparison is dominated by how the two decoders interpolate
    chroma at a hard colour edge, which differs and is not what is being
    measured. Block means keep what the frame is a picture of.
    """
    out = []
    for top in range(0, height - side + 1, side):
        for left in range(0, width - side + 1, side):
            for channel in range(3):
                total = 0
                for y in range(top, top + side):
                    base = (y * width + left) * 3 + channel
                    total += sum(frame[base + x * 3] for x in range(side))
                out.append(total / (side * side))
    return out


def distance(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


with tempfile.TemporaryDirectory(prefix='horos-mpeg4-frames-') as tmp:
    work = Path(tmp)
    (work / 'main.swift').write_text(harness)
    subprocess.run(['xcrun', 'swiftc', '-O',
                    str(root / 'Horos/Sources/H264StreamDecoder.swift'),
                    str(root / 'Horos/Sources/H264PictureOrder.swift'),
                    str(work / 'main.swift'), '-o', str(work / 'decode')], check=True)

    for number, argument in enumerate(sys.argv[1:]):
        fixture = Path(argument).resolve()
        instances = sorted(fixture.glob('*.dcm'))
        assert len(instances) == 1, '%s holds %d instances' % (fixture, len(instances))
        dataset = pydicom.dcmread(str(instances[0]))
        assert str(dataset.file_meta.TransferSyntaxUID) == '1.2.840.10008.1.2.4.102', \
            '%s is not MPEG-4 AVC' % instances[0]

        # One fragment for the whole video, which is what the syntax requires:
        # the frames are not one per fragment, and the first item is the basic
        # offset table, which is empty.
        items = list(pydicom.encaps.generate_fragments(dataset.PixelData))
        assert items[0] == b'', 'the basic offset table is not empty'
        fragments = [item for item in items[1:] if item]
        assert len(fragments) == 1, '%d fragments' % len(fragments)
        stream = work / ('%d.h264' % number)
        stream.write_bytes(fragments[0])

        for shuffled in (False, True):
            frames = work / ('%d-%s' % (number, 'shuffled' if shuffled else 'ordered'))
            reported = subprocess.run(
                [str(work / 'decode'), str(stream), str(frames)]
                + (['--shuffled'] if shuffled else []),
                check=True, capture_output=True, text=True).stdout.split()
            count, width, height = (int(x) for x in reported[:3])
            assert reported[3] == 'true', 'the display order was not read from the stream'
            assert (width, height) == (dataset.Columns, dataset.Rows), \
                'decoded %dx%d, the header says %dx%d' % (width, height,
                                                          dataset.Columns, dataset.Rows)
            assert count == dataset.NumberOfFrames, \
                '%d frames decoded, %d declared' % (count, dataset.NumberOfFrames)

            raw = work / ('%d.raw' % number)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(stream),
                            '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-y', str(raw)], check=True)
            size = width * height * 3
            data = raw.read_bytes()
            assert len(data) == size * count, 'ffmpeg decoded %d frames' % (len(data) / size)
            reference = [blocks(data[i * size:(i + 1) * size], width, height)
                         for i in range(count)]

            worst = 0.0
            for index in range(count):
                mine = blocks((frames / ('%04d.rgb' % index)).read_bytes(), width, height)
                own = distance(mine, reference[index])
                worst = max(worst, own)
                for other in (index - 1, index + 1):
                    if 0 <= other < count:
                        assert own < distance(mine, reference[other]), (
                            'frame %d of %s is closer to frame %d: the frames are '
                            'not in the order they are shown' % (index, fixture.name, other))
            print('%-34s %2d frames %dx%d %s, worst block difference %.2f of 255'
                  % (fixture.name, count, width, height,
                     'out of order' if shuffled else 'in order', worst))
            assert worst < 12, 'the frames do not match ffmpeg'

print('PASS: every frame decodes to the picture it should, asked for in order and out of it')
