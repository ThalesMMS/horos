#!/usr/bin/env python3
"""Image arithmetic with a pixel shift writes every pixel, and reads the shifted image (#675).

-[DCMPix arithmeticSubtractImages::absolute:] and -[DCMPix multiplyImages::],
the arithmetic of a fused series, built their result in an uninitialised
buffer. With a pixel shift (subPixOffset) they wrote only the rows and the
columns the shifted image covers, from column 0 whatever the shift, reading
the shifted image from column -dx: a shift to the right wrote its first
columns with the end of the previous row and left its last ones unwritten.

The methods are compiled here from the source, in a stand-in DCMPix with the
fields they read; every block they allocate with malloc starts out as a large
value, so that memory they never write cannot pass for zero. Each shift -
none, along x, along y, both, both signs - is compared, for the subtraction,
its absolute value and the product, with an independent computation: under
pixel (x, y) the other image's pixel (x - dx, y + dy), as subtractImages::
reads the mask (#669); where the shifted image has no pixel, 0.

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


methods = '\n'.join(braced(source, source.index(signature)) for signature in (
    '-(float*) multiplyImages :(float*) input :(float*) subfImage',
    '-(float*) arithmeticSubtractImages :(float*) input :(float*) subfImage absolute:(BOOL) abs'))
WIDTH, HEIGHT = 23, 17
SHIFTS = [(0, 0), (3, 0), (-3, 0), (0, 2), (0, -2), (2, -1), (-4, 3), (5, 5)]

harness = r'''
#import <Foundation/Foundation.h>
#import <Accelerate/Accelerate.h>
#include <math.h>
void vmultiplyNoAltivec(float *a, float *b, float *r, long size) { for (long k = 0; k < size; ++k) r[k] = a[k] * b[k]; }
void vsubtractNoAltivec(float *a, float *b, float *r, long size) { for (long k = 0; k < size; ++k) r[k] = a[k] - b[k]; }
void vsubtractNoAltivecAbs(float *a, float *b, float *r, long size) { for (long k = 0; k < size; ++k) r[k] = fabsf(a[k] - b[k]); }
@interface Pix : NSObject {
@public
    long height, width;
    NSPoint subPixOffset;
}
@end
// Every block the methods allocate with malloc starts out as a large value, so
// that memory they never write cannot pass for zero.
static void *scribbled_malloc(size_t size) { float *block = malloc(size); for (size_t k = 0; k < size / sizeof(float); ++k) block[k] = 1.0e6f; return block; }
#define malloc(size) scribbled_malloc(size)
@implementation Pix
METHODS
@end
#undef malloc
int main() { @autoreleasepool {
    long width = WIDTH, height = HEIGHT, count = width * height;
    NSMutableArray *runs = [NSMutableArray array];
    for (NSArray *shift in SHIFTLIST) {
        Pix *pix = [Pix new];
        pix->width = width; pix->height = height;
        pix->subPixOffset = NSMakePoint([shift[0] doubleValue], [shift[1] doubleValue]);
        float *a = (float *)malloc(count * sizeof(float)), *b = (float *)malloc(count * sizeof(float));
        for (long k = 0; k < count; ++k) { long x = k % width, y = k / width; a[k] = 3 * x + 5 * y + 1; b[k] = 2 * x - y + 7 + (x * y % 5); }
        NSMutableDictionary *entry = [NSMutableDictionary dictionaryWithObject:shift forKey:@"shift"];
        float *results[3] = { [pix arithmeticSubtractImages:a :b absolute:NO], [pix arithmeticSubtractImages:a :b absolute:YES], [pix multiplyImages:a :b] };
        NSArray *names = @[@"subtract", @"absolute", @"multiply"];
        for (int r = 0; r < 3; ++r) {
            NSMutableArray *values = [NSMutableArray arrayWithCapacity:count];
            for (long k = 0; k < count; ++k) [values addObject:isfinite(results[r][k]) ? @(results[r][k]) : @"nan"];
            entry[names[r]] = values;
        }
        [runs addObject:entry];
    }
    printf("%s\n", [[[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:runs options:0 error:nil] encoding:NSUTF8StringEncoding] UTF8String]);
} return 0; }
'''.replace('METHODS', methods).replace('WIDTH', str(WIDTH)).replace('HEIGHT', str(HEIGHT)) \
   .replace('SHIFTLIST', '@[' + ', '.join('@[@(%d), @(%d)]' % s for s in SHIFTS) + ']')

with tempfile.TemporaryDirectory() as work:
    program = Path(work) / 'arithmetic.m'
    program.write_text(harness)
    binary = Path(work) / 'arithmetic'
    built = subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-x', 'objective-c', str(program),
                            '-framework', 'Foundation', '-framework', 'Accelerate', '-o', str(binary)], capture_output=True, text=True)
    if built.returncode:
        sys.exit('FAIL: the harness does not build:\n' + built.stderr[-3000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True)
    if run.returncode:
        sys.exit('FAIL: the harness stopped: ' + run.stderr[-2000:])
    runs = json.loads(run.stdout)

operations = {'subtract': lambda a, b: a - b, 'absolute': lambda a, b: abs(a - b), 'multiply': lambda a, b: a * b}
failures = []
for entry in runs:
    dx, dy = entry['shift']
    for name, operation in operations.items():
        worst, where = 0.0, None
        for k, value in enumerate(entry[name]):
            x, y = k % WIDTH, k // WIDTH
            mx, my = x - dx, y + dy
            covered = 0 <= mx < WIDTH and 0 <= my < HEIGHT
            expected = operation(3 * x + 5 * y + 1, 2 * mx - my + 7 + (mx * my % 5)) if covered else 0.0
            error = float('inf') if value == 'nan' else abs(value - expected)
            if error > worst: worst, where = error, (x, y, value, expected)
        if worst > 1e-3:
            failures.append('%s, shift (%d, %d): pixel (%d, %d) is %s, the shifted image gives %.3f' % (name, dx, dy, *where))

if failures:
    for failure in failures:
        print('FAIL: ' + failure)
    sys.exit(1)
print('ok: image arithmetic with a pixel shift reads the shifted image and writes every pixel (#675)')
