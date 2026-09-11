#!/usr/bin/env python3
"""A PALETTE COLOR frame decodes to the colours its own lookup table names.

Reads every frame of the palette fixture with the built DCM framework - the
decoding path the viewer uses - and compares each sample against the colour the
file's own table gives that pixel's index. A frame that comes back short, or
half a picture, fails on its length before its colours are looked at.

Usage: python test-palette-pixels.py PRODUCTS_DIR PALETTE_FIXTURE_DIR
       PRODUCTS_DIR is build/Build/Products/Debug, holding DCM.framework
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv) < 3:
    print('skipped: needs the built DCM framework and a palette fixture: '
          'PRODUCTS_DIR PALETTE_FIXTURE_DIR', file=sys.stderr)
    raise SystemExit(2)

products = Path(sys.argv[1]).resolve()
fixture = Path(sys.argv[2]).resolve()

for candidate in Path('/private/tmp').glob('*/*/*/scratchpad/*venv*/bin/python'):
    if subprocess.run([str(candidate), '-c', 'import pydicom'],
                      capture_output=True).returncode == 0:
        interpreter = str(candidate)
        break
else:
    raise SystemExit('this test needs an interpreter with pydicom')

reader = r'''
import json, sys
import pydicom

ds = pydicom.dcmread(sys.argv[1])
descriptor = [int(v) for v in ds.RedPaletteColorLookupTableDescriptor]
count, first, bits = descriptor
if count == 0:
    count = 65536


def table(data, bits):
    if bits <= 8 and len(data) >= count * 2:
        # A table written as 16-bit words holding 8-bit values.
        bits = 16
    if bits <= 8:
        return list(data[:count])
    return [int.from_bytes(data[i * 2:i * 2 + 2], 'little') for i in range(count)]


red = table(bytes(ds.RedPaletteColorLookupTableData), bits)
green = table(bytes(ds.GreenPaletteColorLookupTableData), bits)
blue = table(bytes(ds.BluePaletteColorLookupTableData), bits)
print(json.dumps({
    'rows': int(ds.Rows), 'columns': int(ds.Columns),
    'frames': int(getattr(ds, 'NumberOfFrames', 1)),
    'bitsAllocated': int(ds.BitsAllocated),
    'descriptor': descriptor, 'entryBits': bits,
    'red': red, 'green': green, 'blue': blue,
    'indices': [int(v) for v in ds.pixel_array.reshape(-1)],
}))
'''

program = r'''
#import <Foundation/Foundation.h>
#import <DCM/DCM.h>

// One frame as decimal samples, in the order the decoded data holds them.
int main(int argc, char **argv) { @autoreleasepool {
    DCMObject *object = [DCMObject objectWithContentsOfFile:
                            [NSString stringWithUTF8String: argv[1]] decodingPixelData: NO];
    if (object == nil) { fprintf(stderr, "unreadable\n"); return 2; }

    DCMPixelDataAttribute *attribute = (DCMPixelDataAttribute*) [object attributeWithName:@"PixelData"];
    if (attribute == nil) { fprintf(stderr, "no pixel data\n"); return 2; }

    NSData *frame = [attribute decodeFrameAtIndex: atoi(argv[2])];
    if (frame == nil) { fprintf(stderr, "decoded to nothing\n"); return 3; }

    const unsigned char *samples = (const unsigned char*) [frame bytes];
    NSMutableString *out = [NSMutableString stringWithString:@"["];
    for (NSUInteger i = 0; i < [frame length]; i++)
        [out appendFormat: i ? @",%u" : @"%u", (unsigned) samples[i]];
    [out appendString:@"]"];
    printf("%s\n", [out UTF8String]);
    return 0;
}}
'''

# A palette image says one sample per pixel and means it: the samples are
# indices. The guard that reads a colour header with one sample per pixel as
# grey - which is right for an ultrasound whose header lies - therefore has to
# ask the frame, not the header, or every palette image comes back grey.
pix = (Path(__file__).resolve().parents[1] / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')
guard = pix[pix.index('int samplesPerPixel = [[dcmObject attributeValueWithName: @"SamplesperPixel"]'):]
guard = guard[:guard.index('if (isRGB == YES)')]
assert 'frameCarriesThreeSamples' in guard, (
    'the colour guard still asks only the header, so a palette image reads as grey')
assert '[pixData length] >= (long) height * (long) width * 3L' in guard, (
    'the guard does not measure the decoded frame')
assert 'samplesPerPixel == 1' in guard, (
    'the header check is gone, so a grey picture claiming RGB reads as colour')

with tempfile.TemporaryDirectory(prefix='horos-palette-pixels-') as tmp:
    p = Path(tmp)
    (p / 'bin').mkdir()
    (p / 'Frameworks').symlink_to(products)
    (p / 'read.m').write_text(program)
    (p / 'describe.py').write_text(reader)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fmodules',
                    '-F', str(products), '-framework', 'DCM', '-framework', 'Foundation',
                    str(p / 'read.m'), '-o', str(p / 'bin/read')], check=True)

    files = sorted(f for f in fixture.glob('*.dcm'))
    assert files, f'no files in {fixture}'
    checked = 0

    for path in files:
        described = json.loads(subprocess.check_output(
            [interpreter, str(p / 'describe.py'), str(path)], text=True))
        rows, columns = described['rows'], described['columns']
        frames = described['frames']
        first, entryBits = described['descriptor'][1], described['entryBits']
        red, green, blue = described['red'], described['green'], described['blue']
        indices = described['indices']
        pixels = rows * columns
        # The descriptor says how wide an entry is, not how much of it is used.
        # A nuclear medicine palette commonly stores 0-255 in 16-bit words, so
        # the production code decides by the largest value in all three tables,
        # and this has to ask the same question to expect the same answer.
        largest = max(max(red), max(green), max(blue))
        shift = 0 if largest <= 255 else 8

        for frame in range(frames):
            out = subprocess.run([str(p / 'bin/read'), str(path), str(frame)],
                                 capture_output=True, text=True)
            assert out.returncode == 0, f'{path.name} frame {frame}: {out.stderr.strip()}'
            decoded = json.loads(out.stdout)

            # Half a picture fails here, before any colour is looked at.
            assert len(decoded) == pixels * 3, (
                f'{path.name} frame {frame}: {len(decoded)} samples, '
                f'{pixels * 3} expected for {columns} x {rows} RGB')

            frame_indices = indices[frame * pixels:(frame + 1) * pixels]
            worst = 0
            for pixel, index in enumerate(frame_indices):
                entry = min(max(index - first, 0), len(red) - 1)
                for channel, table in enumerate((red, green, blue)):
                    expected = (table[entry] >> shift) & 0xff
                    got = decoded[pixel * 3 + channel]
                    worst = max(worst, abs(expected - got))
            assert worst <= 1, (
                f'{path.name} frame {frame}: a channel is off by {worst} levels')
            checked += 1

print(f'PASS: {checked} frame(s) across {len(files)} palettes decode to their own '
      'table, at full size')
