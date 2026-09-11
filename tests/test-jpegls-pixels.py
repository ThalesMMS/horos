#!/usr/bin/env python3
"""JPEG-LS frames decode to the pixels the file was built from.

Reads the fixture with the built DCM framework - the same decoding path the
viewer uses - and compares every sample against the reference the generator
wrote. Needs that framework and the fixture, which this repository does not
carry.

Usage: python test-jpegls-pixels.py PRODUCTS_DIR JPEGLS_FIXTURE_DIR
       PRODUCTS_DIR is build/Build/Products/Debug, holding DCM.framework
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv) < 3:
    print('skipped: needs the built DCM framework and a JPEG-LS fixture: '
          'PRODUCTS_DIR JPEGLS_FIXTURE_DIR', file=sys.stderr)
    raise SystemExit(2)

root = Path(__file__).resolve().parents[1]
products = Path(sys.argv[1]).resolve()
fixture = Path(sys.argv[2]).resolve()
reference = json.loads((fixture / 'reference.json').read_text())

program = r'''
#import <Foundation/Foundation.h>
#import <DCM/DCM.h>

// Prints one frame as decimal samples, in the order the data holds them, so the
// comparison is against the bytes the viewer would draw rather than against a
// picture of them.
int main(int argc, char **argv) { @autoreleasepool {
    DCMObject *object = [DCMObject objectWithContentsOfFile:
                            [NSString stringWithUTF8String: argv[1]] decodingPixelData: NO];
    if (object == nil) { fprintf(stderr, "unreadable\n"); return 2; }

    DCMPixelDataAttribute *attribute = (DCMPixelDataAttribute*) [object attributeWithName:@"PixelData"];
    if (attribute == nil) { fprintf(stderr, "no pixel data\n"); return 2; }

    NSData *frame = [attribute decodeFrameAtIndex: 0];
    if (frame == nil) { fprintf(stderr, "decoded to nothing\n"); return 3; }

    int bits = [[object attributeValueWithName:@"BitsAllocated"] intValue];
    NSMutableString *out = [NSMutableString stringWithString:@"["];
    if (bits == 8) {
        const unsigned char *samples = (const unsigned char*) [frame bytes];
        for (NSUInteger i = 0; i < [frame length]; i++)
            [out appendFormat: i ? @",%u" : @"%u", (unsigned) samples[i]];
    } else {
        const unsigned short *samples = (const unsigned short*) [frame bytes];
        for (NSUInteger i = 0; i < [frame length] / 2; i++)
            [out appendFormat: i ? @",%u" : @"%u", (unsigned) samples[i]];
    }
    [out appendString:@"]"];
    printf("%s\n", [out UTF8String]);
    return 0;
}}
'''


def flatten(values):
    if values and isinstance(values[0], list):
        return [sample for row in values for sample in flatten(row)]
    return list(values)


with tempfile.TemporaryDirectory(prefix='horos-jpegls-pixels-') as tmp:
    p = Path(tmp)
    (p / 'bin').mkdir()
    (p / 'Frameworks').symlink_to(products)
    (p / 'read.m').write_text(program)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fmodules',
                    '-F', str(products), '-framework', 'DCM', '-framework', 'Foundation',
                    str(p / 'read.m'), '-o', str(p / 'bin/read')], check=True)

    def samples(name):
        out = subprocess.run([str(p / 'bin/read'), str(fixture / name)],
                             capture_output=True, text=True)
        assert out.returncode == 0, f'{name}: {out.stderr.strip() or out.returncode}'
        return json.loads(out.stdout)

    mono = flatten(reference['mono'])
    rgb = flatten(reference['rgb'])

    # The uncompressed series is the reference read back through the same path,
    # so a difference below is the decoder and not the reader.
    assert samples('uncompressed.dcm') == mono, 'the uncompressed reference does not read back'

    # Lossless is lossless: every sample, not a summary of them.
    assert samples('mono-lossless.dcm') == mono, '16-bit lossless changed the pixels'

    # The same RGB picture encoded three ways. Only "none" splits the
    # components into separate scans, and that is the one that used to decode
    # to nothing; all three have to give the same samples in the same order.
    for name in ('rgb-sample.dcm', 'rgb-line.dcm', 'rgb-none.dcm'):
        decoded = samples(name)
        assert len(decoded) == len(rgb), (
            f'{name} gave {len(decoded)} samples, {len(rgb)} expected')
        assert decoded == rgb, f'{name} changed the pixels or their order'

    # Near-lossless is within the error the file declares, and no further.
    error = reference['nearLosslessError']
    near = samples('mono-nearlossless.dcm')
    assert len(near) == len(mono)
    worst = max(abs(a - b) for a, b in zip(near, mono))
    assert worst <= error, f'near-lossless differs by {worst}, at most {error} allowed'
    assert worst > 0, 'near-lossless is identical, so the allowed error was not exercised'

print(f'PASS: {len(mono)} mono samples and {len(rgb)} RGB samples decode exactly, '
      f'near-lossless within {reference["nearLosslessError"]}')
