#!/usr/bin/env python3
"""Grey ultrasound came back green and purple, and colour came back wrong.

Measured on nine layouts of the same picture - red rising, green falling, blue a
constant 96, and grey ones carrying the same ramp in all three channels - as the
largest distance between the thumbnail the application writes and the colours the
file carries:

    MONOCHROME2 ultrasound                                      5.7    5.7    5.7
    RGB with the samples interleaved                           10.0   10.0    4.0
    RGB stored plane by plane                                  10.0   10.0    4.0
    YBR_FULL with the samples interleaved                      17.3   21.9    5.0
    YBR_FULL stored plane by plane                             17.3   21.9    5.0
    RGB samples in 16-bit words, 8 bits stored                153.1  194.6   55.7
    a grey picture whose header says RGB                      123.7  145.2  145.3
    YBR_FULL_422, two luminance per chrominance pair          140.1  144.7   40.1
    a grey picture stored as YBR_FULL_422                     141.7  149.0  146.4

Four defects:

* `YBR_FULL` was converted with the partial-range matrix - `38142*(Y-16)` is the
  studio-swing scaling - which is a contrast stretch of up to 22 levels.
* `YBR_FULL_422` was not converted at all: Y, Cb and Cr were copied straight into
  R, G and B. A grey ultrasound has Cb and Cr both 128, so it came out green and
  purple, which is what the reports describe.
* An object declaring `BitsAllocated` 16 with `BitsStored` 8 and RGB samples had
  `bitsAllocated` forced to 8 without the pixels being repacked, so three bytes
  were read where six were stored.
* An object whose photometric interpretation says RGB while carrying one sample
  per pixel was read as three, turning a grey picture into a coloured one.

All nine are now within 13 levels.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
attribute = (root / 'DCM Framework/DCMPixelDataAttribute.mm').read_bytes().decode('latin1')
pix = (root / 'Horos/Sources/DCMPix.m').read_bytes().decode('latin1')


def strip(text):
    text = re.sub(r'//[^\n]*', '', text)
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)


# --- one matrix, in one place --------------------------------------------------
at = attribute.find('static inline void ybrToRGB(')
if at < 0:
    failures.append('there is no single place where a luminance and two chrominance samples '
                    'become a colour')
    matrix = ''
else:
    end = attribute.index('\n}\n', at)
    matrix = attribute[at:end + 3]
    for coefficient in ('45941', '23401', '11277', '58065'):
        if coefficient not in matrix:
            failures.append('the full-range matrix is missing %s, so YBR_FULL is still '
                            'converted as if its luminance were studio range' % coefficient)
    for coefficient in ('38142', '52298', '26640', '12845', '66093'):
        if coefficient not in matrix:
            failures.append('the partial-range matrix lost %s' % coefficient)

convert = strip(attribute[attribute.find('- (NSData *) convertYBrToRGB:'):][:6000])
if not convert:
    failures.append('-convertYBrToRGB:kind:isPlanar: is gone')
else:
    if 'ybrToRGB(' not in convert:
        failures.append('the conversion does not go through the shared matrix, so the layouts '
                        'can disagree about what a colour is')
    if '_422' not in convert:
        failures.append('the subsampled layout is no longer recognised, and copying its samples '
                        'straight through is what made a grey ultrasound green and purple')
    if 'hasPrefix: @"YBR_PARTIAL"' not in convert:
        failures.append('nothing tells the two ranges apart')

# --- and the two decisions in the reader ---------------------------------------
code = strip(pix)
at = code.find('if (isRGB == YES)')
window = code[max(at - 1200, 0):at + 900] if at >= 0 else ''
if not window:
    failures.append('the colour branch of the reader is gone')
else:
    if 'SamplesperPixel' not in window:
        failures.append('a photometric interpretation that says RGB is still believed over the '
                        'number of samples the object carries')
    if 'height * width * 3 * 2' not in window:
        failures.append('the width of a sample still comes from what the object declares rather '
                        'than from how many bytes it carries')
    if 'bitsAllocated > 8' in window:
        failures.append('the colour branch still chooses by the declared bits')

# --- the matrix answers what the standard says ---------------------------------
if matrix:
    DRIVER = '''
#import <Foundation/Foundation.h>
#include <cstdio>
MATRIX
int main() {
    unsigned char r, g, b;
    // Grey: Cb and Cr at 128 leave the luminance alone in full range.
    ybrToRGB(0, 128, 128, NO, &r, &g, &b);    printf("%d %d %d\\n", r, g, b);
    ybrToRGB(128, 128, 128, NO, &r, &g, &b);  printf("%d %d %d\\n", r, g, b);
    ybrToRGB(255, 128, 128, NO, &r, &g, &b);  printf("%d %d %d\\n", r, g, b);
    // Pure red, green and blue, converted to YBR_FULL and back.
    ybrToRGB(76, 85, 255, NO, &r, &g, &b);    printf("%d %d %d\\n", r, g, b);
    ybrToRGB(150, 44, 21, NO, &r, &g, &b);    printf("%d %d %d\\n", r, g, b);
    ybrToRGB(29, 255, 107, NO, &r, &g, &b);   printf("%d %d %d\\n", r, g, b);
    // Partial range: 16 is black and 235 is white.
    ybrToRGB(16, 128, 128, YES, &r, &g, &b);  printf("%d %d %d\\n", r, g, b);
    ybrToRGB(235, 128, 128, YES, &r, &g, &b); printf("%d %d %d\\n", r, g, b);
    // The corners of the cube, where the matrix runs off both ends and has to
    // be clamped rather than wrapped.
    ybrToRGB(255, 255, 255, NO, &r, &g, &b);  printf("%d %d %d\\n", r, g, b);
    ybrToRGB(0, 0, 0, NO, &r, &g, &b);        printf("%d %d %d\\n", r, g, b);
    return 0;
}
'''.replace('MATRIX', matrix)
    with tempfile.TemporaryDirectory(prefix='horos-ybr-') as directory:
        main = Path(directory) / 'main.mm'
        main.write_text(DRIVER)
        binary = Path(directory) / 'ybr'
        build = subprocess.run(['xcrun', 'clang++', '-std=c++11', '-w', '-framework',
                                'Foundation', str(main), '-o', str(binary)],
                               capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('the matrix does not compile:\n%s' % build.stderr[-800:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
            got = [line.split() for line in run.stdout.splitlines()]
            want = [['0', '0', '0'], ['128', '128', '128'], ['255', '255', '255'],
                    ['254', '0', '0'], ['1', '255', '1'], ['0', '0', '254'],
                    ['0', '0', '0'], ['255', '255', '255'],
                    # Y=Cb=Cr=255 is not white: red and blue run past the top and
                    # are clamped, green falls to 121.
                    ['255', '121', '255'], ['0', '135', '0']]
            for index, (a, b) in enumerate(zip(got, want)):
                # A byte of slack: the fixed point rounds.
                if len(a) != 3 or any(abs(int(x) - int(y)) > 1 for x, y in zip(a, b)):
                    failures.append('case %d converts to %r, expected about %r' % (index, a, b))
            if len(got) != len(want):
                failures.append('the driver produced %d of %d cases' % (len(got), len(want)))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: one matrix converts every YBR layout, a grey object is read as grey whatever its '
      'header says, and a sample is as wide as the pixels are')
