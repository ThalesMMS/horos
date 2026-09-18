#!/usr/bin/env python3
"""A subtraction with a pixel shift writes every pixel, and subtracts the shifted mask (#669).

-[DCMPix subtractImages::] (the angiography subtraction) built its result in
an uninitialised buffer. With a pixel shift (subPixOffset, the manual mask
registration) it copied the mask at an offset but subtracted from the start of
the buffer: the first pixels subtracted memory nothing had written, the last
ones kept the mask without the frame, and a horizontal shift wrapped into the
neighbouring row.

The method is compiled here from the source, in a stand-in DCMPix with the
fields it reads; every block it allocates starts out as a large value, so
that memory it never writes cannot pass for zero. Each shift - none, along x, along y, both, both signs -
is compared with an independent subtraction: under frame pixel (x, y) the
mask pixel (x - dx, y + dy), as the host's other image arithmetic reads it,
weighted by the mask percentage; where the shifted mask has no pixel, no
difference; then the host's normalisation.

`<git revision>` as an optional argument reads the source from that revision,
the negative control.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/DCMPix.m'
source = (subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]) if len(sys.argv) > 1
          else (root / path).read_bytes()).decode('latin1')


def braced(text, start):
    depth, index = 0, text.index('{', start)
    while True:
        if text[index] == '{': depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0: return text[start:index + 1]
        index += 1


method = braced(source, source.index('-(float*) subtractImages:(float*)input :(float*)subfImage'))
WIDTH, HEIGHT, PERCENT, ZERO, LOW, HIGH = 23, 17, 0.75, 0.8, -40.0, 60.0
SHIFTS = [(0, 0), (3, 0), (-3, 0), (0, 2), (0, -2), (2, -1), (-4, 3), (5, 5)]

harness = r'''
#import <Foundation/Foundation.h>
#import <Accelerate/Accelerate.h>
#include <math.h>
@interface Pix : NSObject {
@public
    long height, width;
    NSPoint subPixOffset, subMinMax;
    float subtractedfPercent, subtractedfZero;
    float *fImage;
}
-(float*) subtractImages:(float*)input :(float*)subfImage;
@end
// Every block the method allocates starts out as a large value, so that
// memory it never writes cannot pass for zero.
static void *scribbled_malloc(size_t size) { float *block = malloc(size); for (size_t k = 0; k < size / sizeof(float); ++k) block[k] = 1.0e6f; return block; }
#define malloc(size) scribbled_malloc(size)
@implementation Pix
METHOD
@end
#undef malloc
int main() { @autoreleasepool {
    long width = WIDTH, height = HEIGHT, count = width * height;
    NSMutableArray *runs = [NSMutableArray array];
    for (NSArray *shift in SHIFTLIST) {
        Pix *pix = [Pix new];
        pix->width = width; pix->height = height;
        pix->subPixOffset = NSMakePoint([shift[0] doubleValue], [shift[1] doubleValue]);
        pix->subMinMax = NSMakePoint(LOW, HIGH);
        pix->subtractedfPercent = PERCENT; pix->subtractedfZero = ZERO;
        float *frame = (float *)malloc(count * sizeof(float)), *mask = (float *)malloc(count * sizeof(float));
        for (long k = 0; k < count; ++k) { long x = k % width, y = k / width; frame[k] = 3 * x + 5 * y + 1; mask[k] = 2 * x - y + 7 + (x * y % 5); }
        pix->fImage = frame;
        float *input = (float *)malloc(count * sizeof(float)); memcpy(input, frame, count * sizeof(float));
        float *result = [pix subtractImages:input :mask];
        NSMutableArray *values = [NSMutableArray arrayWithCapacity:count];
        for (long k = 0; k < count; ++k) [values addObject:isfinite(result[k]) ? @(result[k]) : @"nan"];
        [runs addObject:@{@"shift": shift, @"values": values}];
    }
    printf("%s\n", [[[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:runs options:0 error:nil] encoding:NSUTF8StringEncoding] UTF8String]);
} return 0; }
'''.replace('METHOD', method).replace('WIDTH', str(WIDTH)).replace('HEIGHT', str(HEIGHT)).replace('PERCENT', repr(PERCENT)) \
   .replace('ZERO', repr(ZERO)).replace('LOW', repr(LOW)).replace('HIGH', repr(HIGH)) \
   .replace('SHIFTLIST', '@[' + ', '.join('@[@(%d), @(%d)]' % s for s in SHIFTS) + ']')

with tempfile.TemporaryDirectory() as work:
    program = Path(work) / 'subtract.m'
    program.write_text(harness)
    binary = Path(work) / 'subtract'
    built = subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-x', 'objective-c', str(program),
                            '-framework', 'Foundation', '-framework', 'Accelerate', '-o', str(binary)], capture_output=True, text=True)
    if built.returncode:
        sys.exit('FAIL: the harness does not build:\n' + built.stderr[-3000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    if run.returncode:
        sys.exit('FAIL: the harness stopped: ' + run.stderr[-2000:])
    runs = json.loads(run.stdout)

failures = []
ratio = abs(HIGH - LOW)
for entry in runs:
    dx, dy = entry['shift']
    worst, where = 0.0, None
    for k, value in enumerate(entry['values']):
        x, y = k % WIDTH, k // WIDTH
        frame = 3 * x + 5 * y + 1
        mx, my = x - dx, y + dy
        difference = frame - PERCENT * (2 * mx - my + 7 + (mx * my % 5)) if 0 <= mx < WIDTH and 0 <= my < HEIGHT else 0.0
        expected = difference / ratio + ZERO
        error = float('inf') if value == 'nan' else abs(value - expected)
        if error > worst: worst, where = error, (x, y, value, expected)
    if worst > 1e-4:
        failures.append('shift (%d, %d): pixel (%d, %d) is %s, the shifted mask gives %.5f' % (dx, dy, *where))

if failures:
    for failure in failures:
        print('FAIL: ' + failure)
    sys.exit(1)
print('ok: a subtraction with a pixel shift subtracts the shifted mask and writes every pixel (#669)')
