#!/usr/bin/env python3
"""The colour full-depth readback takes each pixel's own colour (#672).

-[VRView imageInFullDepthWidth:height:isRGB:blendingView:] reads VTK's
ray-cast image back as ARGB bytes whenever the result is colour: an RGB
volume's planes in the MPR and the CPR, and the VR's full-depth capture, for
ROIs and for export, a scalar volume in composite included. The image is
RGBA, four unsigned shorts per pixel with R first, and the colour branch
started on the alpha and skipped it: every pixel took the R, G and B of its
right-hand neighbour, and the last of each row read past the width in use.

The colour branch is compiled here from the source and run on a synthetic
ray-cast image whose memory rows are wider than the width in use, with a
distinct colour in every pixel: each output pixel, rows top first, must be
255 and its own R, G and B shifted by 7. The copy in VRView+StereoVision.mm,
which the build leaves out, is held to the same loop.

`<git revision>` as an optional argument reads the sources from that revision,
the negative control.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
revision = sys.argv[1] if len(sys.argv) > 1 else None


def read(path):
    if revision:
        return subprocess.check_output(['git', '-C', str(root), 'show', revision + ':' + path]).decode('latin1')
    return (root / path).read_bytes().decode('latin1')


def braced(text, start):
    depth, index = 0, text.index('{', start)
    while True:
        if text[index] == '{': depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0: return text[start:index + 1]
        index += 1


def colour_branch(source):
    method = source[source.index('- (float*) imageInFullDepthWidth: (long*) w height:(long*) h isRGB:(BOOL*) rgb blendingView:(BOOL) blendingView'):]
    start = method.index('unsigned char *destPtr, *destFixedPtr;')
    allocation = method.index('if( destFixedPtr)', start)
    return method[start:allocation] + braced(method, allocation)


failures = []
branch = colour_branch(read('Horos/Sources/VRView.mm'))
stereo = colour_branch(read('Horos/Sources/VRView+StereoVision.mm'))
if 'unsigned short *iptr = im + 4*(*h-1)*fullSize[0];' not in stereo or 'iptrTemp += 4;' not in stereo:
    failures.append('the copy in VRView+StereoVision.mm does not read each pixel\'s own colour')

WIDTH, HEIGHT, MEMORY_WIDTH, MEMORY_HEIGHT = 7, 5, 10, 7
harness = r'''
#import <Foundation/Foundation.h>
#import <Accelerate/Accelerate.h>
static unsigned char *readback(unsigned short *im, int fullSize[2], long *w, long *h, BOOL *rgb) {
    float *returnedPtr = nil;
    BRANCH
    return (unsigned char *)returnedPtr;
}
int main() { @autoreleasepool {
    int fullSize[2] = {MEMORY_WIDTH, MEMORY_HEIGHT};
    long w = WIDTH, h = HEIGHT; BOOL rgb = NO;
    unsigned short *im = calloc(fullSize[0] * fullSize[1] * 4, sizeof(unsigned short));
    for (int y = 0; y < fullSize[1]; ++y)
        for (int x = 0; x < fullSize[0]; ++x) {
            unsigned short *pixel = im + 4 * (y * fullSize[0] + x);
            pixel[0] = (unsigned short)(128 * (10 * x + y + 1));
            pixel[1] = (unsigned short)(128 * (20 + 7 * x + 3 * y));
            pixel[2] = (unsigned short)(128 * (200 - 9 * x - 5 * y));
            pixel[3] = 32767;
        }
    unsigned char *out = readback(im, fullSize, &w, &h, &rgb);
    NSMutableArray *bytes = [NSMutableArray array];
    for (long k = 0; k < w * h * 4; ++k) [bytes addObject:@(out[k])];
    printf("%s\n", [[[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:@{@"rgb": @(rgb), @"bytes": bytes} options:0 error:nil]
                                             encoding:NSUTF8StringEncoding] UTF8String]);
} return 0; }
'''.replace('BRANCH', branch).replace('MEMORY_WIDTH', str(MEMORY_WIDTH)).replace('MEMORY_HEIGHT', str(MEMORY_HEIGHT)) \
   .replace('WIDTH', str(WIDTH)).replace('HEIGHT', str(HEIGHT))

with tempfile.TemporaryDirectory() as work:
    program = Path(work) / 'readback.m'
    program.write_text(harness)
    binary = Path(work) / 'readback'
    built = subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-x', 'objective-c', str(program),
                            '-framework', 'Foundation', '-framework', 'Accelerate', '-o', str(binary)], capture_output=True, text=True)
    if built.returncode:
        sys.exit('FAIL: the harness does not build:\n' + built.stderr[-3000:])
    result = json.loads(subprocess.run([str(binary)], capture_output=True, text=True, check=True).stdout)

if not result['rgb']:
    failures.append('the colour branch does not report a colour image')
wrong = []
for row in range(HEIGHT):
    y = HEIGHT - 1 - row                      # VTK keeps the bottom row first
    for x in range(WIDTH):
        expected = [255, (10 * x + y + 1), (20 + 7 * x + 3 * y), (200 - 9 * x - 5 * y)]
        got = result['bytes'][4 * (row * WIDTH + x):4 * (row * WIDTH + x) + 4]
        if got != expected:
            wrong.append((x, row, got, expected))
if wrong:
    x, row, got, expected = wrong[0]
    failures.append('%d of %d pixels take another pixel\'s colour; pixel (%d, %d) is %s, its own colour is %s'
                    % (len(wrong), WIDTH * HEIGHT, x, row, got, expected))

if failures:
    for failure in failures:
        print('FAIL: ' + failure)
    sys.exit(1)
print('ok: the colour full-depth readback takes each pixel\'s own colour (#672)')
