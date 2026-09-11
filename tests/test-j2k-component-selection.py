#!/usr/bin/env python3
"""A JPEG 2000 image with alpha must have somewhere to read it from.

The decoder picks which component holds what from the component count. The
outer guard admits numcomps >= 3 and calls the case RGB[A], but the branch test
asked for exactly 3, so a four-component RGBA image fell into the greyscale
branch: all three colours came from comps[0], alpha was never assigned, and the
loop then dereferenced it because hasAlpha was true. Opening such an image
crashed (#531).

This extracts the real flag block and runs it for every component count the
guard admits, requiring that whenever the loop will read alpha there is an
alpha component to read, and that the colours come from distinct components
when there are three or more.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []
source = (root / 'Horos/Sources/OPJSupport.cpp').read_bytes().decode('latin1')

block = re.search(
    r'(has_rgb\s*=\s*\([^;]+;\s*'
    r'has_alpha4\s*=\s*\([^;]+;\s*'
    r'has_alpha2\s*=\s*\([^;]+;\s*'
    r'hasAlpha\s*=\s*\([^;]+;)', source)
if not block:
    print('FAIL: the component flags are gone from OPJSupport.cpp', file=sys.stderr)
    sys.exit(1)

flags = block.group(1)
# The decoder reads the flags through decodeInfo.image->numcomps; drive that
# with a plain count here.
flags = re.sub(r'decodeInfo\.image->numcomps', 'numcomps', flags)

code = '''
#include <stdio.h>
int main(void) {
    int bad = 0;
    // The guard admits three or more components, or exactly two.
    int counts[] = {2, 3, 4, 5};
    for (int c = 0; c < (int)(sizeof(counts)/sizeof(*counts)); ++c) {
        int numcomps = counts[c];
        int has_rgb, has_alpha4, has_alpha2, hasAlpha;
        FLAGS
        // Which component index each channel would be read from, -1 for none.
        int red, green, blue, alpha = -1;
        if (has_rgb) {
            red = 0; green = 1; blue = 2;
            if (has_alpha4) alpha = 3;
        } else {
            red = green = blue = 0;
            if (has_alpha2) alpha = 1;
        }
        if (hasAlpha && alpha < 0) {
            printf("FAIL: %d components will read alpha but none was chosen\\n", numcomps);
            bad = 1;
        }
        if (alpha >= numcomps) {
            printf("FAIL: %d components would read alpha from component %d\\n", numcomps, alpha);
            bad = 1;
        }
        if (numcomps >= 3 && (red == green || green == blue)) {
            printf("FAIL: %d components read colours from one component\\n", numcomps);
            bad = 1;
        }
        if (numcomps == 2 && alpha != 1) {
            printf("FAIL: greyscale+alpha did not take alpha from component 1\\n");
            bad = 1;
        }
    }
    if (!bad) puts("PASS: every admitted component count chooses a readable alpha");
    return bad;
}
'''.replace('FLAGS', flags)

with tempfile.TemporaryDirectory(prefix='horos-j2k-comps-') as tmp:
    path = Path(tmp)
    (path / 'main.c').write_text(code)
    build = subprocess.run(['xcrun', 'clang', str(path / 'main.c'), '-o', str(path / 'test')],
                           capture_output=True, text=True)
    if build.returncode != 0:
        failures.append('the extracted flags do not compile: %s' % build.stderr[-800:])
    else:
        run = subprocess.run([str(path / 'test')], capture_output=True, text=True)
        sys.stdout.write(run.stdout)
        if run.returncode != 0:
            failures.append('a component count leaves alpha unreadable')

if failures:
    for item in failures:
        print('FAIL:', item, file=sys.stderr)
    sys.exit(1)
print('PASS: JPEG 2000 component selection never reads an alpha it did not choose')
