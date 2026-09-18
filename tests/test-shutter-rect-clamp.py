#!/usr/bin/env python3
"""The Shutter button clips the ROI to the image without moving it (#670).

-[ViewerController shutterOnOff:] turns the selected rectangular ROI into the
image's shutter and clips the rectangle to the image. The top-edge clip
corrected the wrong axis: a ROI past the top edge had its height reduced and
its x set to 0, which moved the shutter to the left edge.

The four clipping lines are compiled here from the source, in a stand-in
image, and run on rectangles inside the image and past each edge and corner;
each result must be the rectangle intersected with the image.

`<git revision>` as an optional argument reads the source from that revision,
the negative control.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/ViewerController.m'
source = (subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path]) if len(sys.argv) > 1
          else (root / path).read_bytes()).decode('utf-8', 'replace')

action = source[source.index('- (IBAction) shutterOnOff:(id) sender'):]
start = action.index('//shutterRect inside frame?')
lines = action[start:action.index('p.shutterRect = shutterRect;', start)]
WIDTH, HEIGHT = 200, 150
CASES = [(40, 30, 100, 80), (-20, 30, 100, 80), (40, -25, 100, 80), (150, 30, 100, 80), (40, 120, 100, 80),
         (-20, -25, 100, 80), (150, 120, 100, 80), (-10, -10, 300, 300)]

harness = r'''
#import <Foundation/Foundation.h>
@interface Image : NSObject
@property long pwidth, pheight;
@end
@implementation Image
@end
int main() { @autoreleasepool {
    Image *p = [Image new]; p.pwidth = WIDTH; p.pheight = HEIGHT;
    NSMutableArray *out = [NSMutableArray array];
    double cases[][4] = { CASES };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        NSRect shutterRect = NSMakeRect(cases[i][0], cases[i][1], cases[i][2], cases[i][3]);
        LINES
        [out addObject:@[@(shutterRect.origin.x), @(shutterRect.origin.y), @(shutterRect.size.width), @(shutterRect.size.height)]];
    }
    printf("%s\n", [[[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:out options:0 error:nil] encoding:NSUTF8StringEncoding] UTF8String]);
} return 0; }
'''.replace('LINES', lines).replace('WIDTH', str(WIDTH)).replace('HEIGHT', str(HEIGHT)) \
   .replace('CASES', ', '.join('{%d, %d, %d, %d}' % c for c in CASES))

with tempfile.TemporaryDirectory() as work:
    program = Path(work) / 'clamp.m'
    program.write_text(harness)
    binary = Path(work) / 'clamp'
    built = subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-x', 'objective-c', str(program), '-framework', 'Foundation', '-o', str(binary)],
                           capture_output=True, text=True)
    if built.returncode:
        sys.exit('FAIL: the harness does not build:\n' + built.stderr[-3000:])
    results = json.loads(subprocess.run([str(binary)], capture_output=True, text=True, check=True).stdout)

failures = []
for (x, y, w, h), got in zip(CASES, results):
    x0, y0, x1, y1 = max(0, x), max(0, y), min(WIDTH, x + w), min(HEIGHT, y + h)
    expected = [x0, y0, x1 - x0, y1 - y0]
    if [round(v, 6) for v in got] != expected:
        failures.append('ROI (%d, %d, %d, %d): shutter %s, the ROI clipped to the image is %s' % (x, y, w, h, got, expected))

if failures:
    for failure in failures:
        print('FAIL: ' + failure)
    sys.exit(1)
print('ok: the Shutter button clips the ROI to the image without moving it (#670)')
