#!/usr/bin/env python3
"""PALETTE COLOR: the blue table was read out of the green attribute.

`-[DCMPixelDataAttribute convertPaletteToRGB:]` built its three lookup tables in
three separate blocks, and the blue one read the green attribute's bytes:

    DCMAttribute *blueCLUT = [_dcmObject attributeWithName:@"BluePalette…Data"];
    if (blueCLUT) {
        …
        else{
            unsigned char *ptrs = (unsigned char*) [[greenCLUT value] bytes];

So every paletted image came back with blue equal to green - and an object with a
blue table and no green one dereferenced a null pointer. Beside it, a 16-bit
entry was turned into 8 bits by dividing by 256, which is only right when the
entries really use all sixteen; nuclear medicine equipment that stores 0-255 in
16-bit words produced black. The pixel loop for 16-bit images byte-swapped the
index, so a pixel of 1 asked for entry 256 - past the end of a 256-entry palette
- and neither loop applied the descriptor's first mapped value or clamped the
index to the table.

Measured on five fixtures whose palette is red rising, green falling and blue a
constant 96, as the largest distance between the thumbnail the application wrote
and the table the file carries:

    series                                        red   green    blue
    8-bit palette, 8-bit entries                 11.0     7.0   144.0
    16-bit palette holding 8-bit values         240.0   240.0    96.0
    16-bit palette using all sixteen bits       240.0   240.0    96.0
    12-bit index ramp over 4096 entries         239.0   232.0    96.0
    first entry stands for pixel value 1000     240.0   234.0    97.0

240 out of 255 is the whole picture: black. Afterwards every channel of every
variant is within 11 levels, which is the thumbnail's own rescale and JPEG.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
source = (root / 'DCM Framework/DCMPixelDataAttribute.mm').read_bytes().decode('latin1')


def body(signature, text):
    at = text.find(signature)
    if at < 0:
        return ''
    opening = text.index('{', at)
    depth, index = 0, opening
    while index < len(text):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[opening:index + 1]
        index += 1
    return ''


convert = body('- (NSData *)convertPaletteToRGB:', source)
if not convert:
    failures.append('-convertPaletteToRGB: is gone')
else:
    # Comments describe the defect; they must not be mistaken for it.
    code = re.sub(r'//[^\n]*', '', convert)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)

    windows = [code[at:at + 700]
               for at in range(len(code))
               if code.startswith('BluePaletteColorLookupTableData', at)]
    if not windows:
        failures.append('the blue lookup table is no longer read at all')
    for blue in windows:
        # Everything up to the next attribute belongs to reading the blue one.
        blue = blue.split('PaletteColorLookupTableDescriptor')[0]
        if 'greenCLUT' in blue or 'GreenPaletteColorLookupTableData' in blue:
            failures.append('the blue lookup table is still read from the green attribute, so '
                            'every paletted image comes back with blue equal to green')
            break

    if 'objectAtIndex:1' not in code:
        failures.append('the descriptor\'s first mapped value is ignored, so a palette whose '
                        'first entry stands for a pixel value other than zero is read from the '
                        'wrong end')
    if 'ENTRY_FOR' not in code:
        failures.append('the pixel value is not turned into a table entry in one place, so the '
                        'offset and the clamp can differ between the loops')
    if 'NSSwapBigShortToHost' in code:
        failures.append('a 16-bit palette index is still byte-swapped, which asks for entry 256 '
                        'when the pixel is 1')
    if code.count('/256') or code.count('/ 256'):
        failures.append('a 16-bit table entry is still narrowed by dividing by 256 whatever it '
                        'holds, which turns an 8-bit nuclear medicine palette black')
    if 'largest' not in code:
        failures.append('nothing looks at what the tables actually hold to decide how wide an '
                        'entry is')

# --- the entry lookup itself ---------------------------------------------------
at = source.find('#define ENTRY_FOR')
macro = source[at:source.index('\n\n', at)] if at >= 0 else ''
if not macro:
    failures.append('the entry lookup is gone')
else:
    DRIVER = '''
#include <cstdio>
MACRO

int main() {
    // value, first mapped, entries -> entry
    printf("%ld\\n", (long) ENTRY_FOR(0L, 0, 256));      // the bottom
    printf("%ld\\n", (long) ENTRY_FOR(255L, 0, 256));    // the top
    printf("%ld\\n", (long) ENTRY_FOR(256L, 0, 256));    // past the top, clamped
    printf("%ld\\n", (long) ENTRY_FOR(1000L, 1000, 256));// the first mapped value
    printf("%ld\\n", (long) ENTRY_FOR(1255L, 1000, 256));// the last it maps
    printf("%ld\\n", (long) ENTRY_FOR(999L, 1000, 256)); // below it, clamped
    printf("%ld\\n", (long) ENTRY_FOR(4095L, 0, 4096));  // a 12-bit index
    printf("%ld\\n", (long) ENTRY_FOR(7L, 0, 0));        // no table at all
    return 0;
}
'''.replace('MACRO', macro)
    with tempfile.TemporaryDirectory(prefix='horos-clut-') as directory:
        driver = Path(directory) / 'main.cc'
        driver.write_text(DRIVER)
        binary = Path(directory) / 'clut'
        build = subprocess.run(['xcrun', 'clang++', '-std=c++11', '-w', str(driver),
                                '-o', str(binary)], capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('the entry lookup does not compile:\n%s' % build.stderr[-800:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
            got = run.stdout.split()
            want = ['0', '255', '255', '0', '255', '0', '4095', '0']
            if got != want:
                failures.append('the entry lookup answers %r, expected %r' % (got, want))

for failure in failures:
    print('FAIL: %s' % failure)
if failures:
    sys.exit(1)
print('ok: each palette table is read from its own attribute, an entry is as wide as its values '
      'are, and a pixel becomes an entry through the descriptor with the clamp the standard asks '
      'for')
