#!/usr/bin/env python3
"""The 16-bit value map of VRView stays one affine transform, for every time (#600).

The 3D MPR captures its planes through the CPU ray caster with a linear
opacity table, and decodes each pixel as `value = raw / valueFactor - OFFSET16`.
That only holds when the volume was encoded with the same pair. Two defects
broke it:

* `computeValueFactor` scaled narrow (< 50) and wide (> 32000) ranges but had
  its `OFFSET16` assignment commented out, so a positive narrow range such as
  50..70 was encoded as `50 * 1600`, saturated, and decoded as nothing.
* a 4D set fixed the pair when its first time was loaded; the other times were
  added afterwards and could widen the range without the pair being recomputed,
  and only the first time carried the two guard voxels that make VTK see the
  same scalar range for every time.

This compiles the real `computeValueFactor` and the real
`applyMovieRangeGuardTo16BitVolume` out of `VRView.mm` against stubs, and
checks the wiring in `VRController.mm` and `VRView.mm` textually.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
vrview = (root / 'Horos/Sources/VRView.mm').read_bytes().decode('latin1')
controller = (root / 'Horos/Sources/VRController.mm').read_bytes().decode('latin1')
failures = []


def method(source, signature, terminator='\n}\n'):
    start = source.index(signature)
    return source[start:source.index(terminator, start) + len(terminator)]


compute = method(vrview, '- (void) computeValueFactor\n')
guard = method(vrview, '- (void) applyMovieRangeGuardTo16BitVolume\n')

# --- textual wiring ---------------------------------------------------------
branches = re.findall(r'valueFactor = [^;]+;\s*\n\s*OFFSET16 = -\[controller minimumValue\];', compute)
if len(branches) != 2:
    failures.append('computeValueFactor must set OFFSET16 in both the scaled and the unit branch, found %d' % len(branches))
if re.search(r'//\s*OFFSET16 =', compute):
    failures.append('computeValueFactor still carries a commented-out OFFSET16 assignment')

conversion = '[BrowserController multiThreadedImageConvert: @"FTo16U" :&srcf :&dst8 :-OFFSET16 :1./valueFactor];'
for match in re.finditer(re.escape(conversion), vrview):
    following = vrview[match.end():match.end() + 200]
    if '[self applyMovieRangeGuardTo16BitVolume];' not in following:
        line = vrview.count('\n', 0, match.start()) + 1
        failures.append('FTo16U conversion at VRView.mm:%d is not followed by the 4D range guard' % line)
if vrview.count(conversion) < 4:
    failures.append('expected the main-volume FTo16U conversion at least four times, found %d' % vrview.count(conversion))

if re.search(r'\*\(data\+0\+\[firstObject pwidth\]\) = \[controller minimumValue\]', vrview):
    failures.append('the float volume shared with the 2D viewer is still patched with the 4D guard')

add_movie = method(controller, '-(void) addMoviePixList:(NSMutableArray*) pix :(NSData*) vData\n')
if '[self computeMinMax];' not in add_movie or '[view recomputeValueFactorAfterRangeChange];' not in add_movie:
    failures.append('addMoviePixList must recompute min/max and then the value factor')
elif add_movie.index('[self computeMinMax];') > add_movie.index('[view recomputeValueFactorAfterRangeChange];'):
    failures.append('addMoviePixList recomputes the value factor before the new min/max')

# --- compiled behaviour -----------------------------------------------------
DRIVER = r'''
#import <Foundation/Foundation.h>
#import <Accelerate/Accelerate.h>
#define MAXDYNAMICVALUE 32000.

@interface Pix : NSObject
@property BOOL SUVConverted;
@property long pwidth;
@end
@implementation Pix
@end

@interface Viewer2D : NSObject
@property long maxMovieIndex;
@end
@implementation Viewer2D
@end

@interface Controller : NSObject
@property float minimumValue, maximumValue;
@property (strong) Viewer2D *viewer2D;
@end
@implementation Controller
@end

@interface View : NSObject
{
    Pix *firstObject;
    Controller *controller;
    float valueFactor, OFFSET16;
    BOOL isRGB;
    char *data8;
    vImage_Buffer dst8;
}
- (void) computeValueFactor;
- (void) applyMovieRangeGuardTo16BitVolume;
- (instancetype) initWithMin:(float) mn max:(float) mx times:(long) times width:(long) w voxels:(long) n;
- (float) valueFactor;
- (float) OFFSET16;
- (unsigned short*) volume16;
- (void) convert:(const float*) src count:(long) n;
@end

@implementation View
- (instancetype) initWithMin:(float) mn max:(float) mx times:(long) times width:(long) w voxels:(long) n
{
    self = [super init];
    firstObject = [Pix new]; firstObject.pwidth = w;
    controller = [Controller new]; controller.minimumValue = mn; controller.maximumValue = mx;
    controller.viewer2D = [Viewer2D new]; controller.viewer2D.maxMovieIndex = times;
    data8 = (char*) calloc(n, sizeof(unsigned short));
    dst8.data = data8; dst8.width = w; dst8.height = n / w; dst8.rowBytes = w * 2;
    valueFactor = 1; OFFSET16 = 0;
    return self;
}
- (float) valueFactor { return valueFactor; }
- (float) OFFSET16 { return OFFSET16; }
- (unsigned short*) volume16 { return (unsigned short*) data8; }
- (void) convert:(const float*) src count:(long) n
{
    unsigned short *out = (unsigned short*) data8;
    for (long i = 0; i < n; i++) {
        float v = (src[i] + OFFSET16) * valueFactor;
        out[i] = v < 0 ? 0 : (v > 65535 ? 65535 : (unsigned short) (v + 0.5f));
    }
}
''' + compute + guard + r'''
@end

#define CHECK(cond, ...) do { if (!(cond)) { fprintf(stderr, "FAIL: " __VA_ARGS__); fputc('\n', stderr); return 1; } } while (0)

int main(void) { @autoreleasepool {
    // narrow positive range, the #600 phantom: 50..70 on its own
    View *narrow = [[View alloc] initWithMin:50 max:70 times:1 width:4 voxels:16];
    [narrow computeValueFactor];
    CHECK(fabsf(narrow.OFFSET16 - (-50)) < 1e-6, "narrow range OFFSET16 = %f, expected -50", narrow.OFFSET16);
    CHECK(fabsf(narrow.valueFactor - 1600) < 1e-3, "narrow range valueFactor = %f, expected 1600", narrow.valueFactor);
    float samples[16]; for (int i = 0; i < 16; i++) samples[i] = 50;
    samples[3] = 70;
    [narrow convert:samples count:16];
    CHECK(narrow.volume16[0] == 0, "50 must encode to 0, got %u", narrow.volume16[0]);
    CHECK(narrow.volume16[3] == 32000, "70 must encode to 32000, got %u", narrow.volume16[3]);
    float decoded = narrow.volume16[3] / narrow.valueFactor - narrow.OFFSET16;
    CHECK(fabsf(decoded - 70) < 1e-3, "round trip of 70 gave %f", decoded);
    // single time: no guard voxels touched
    [narrow applyMovieRangeGuardTo16BitVolume];
    CHECK(narrow.volume16[4] == 0 && narrow.volume16[5] == 0, "a 3D volume must not receive guard voxels");

    // ordinary CT range keeps the unit factor with the negative offset
    View *ct = [[View alloc] initWithMin:-1000 max:1000 times:1 width:4 voxels:16];
    [ct computeValueFactor];
    CHECK(ct.valueFactor == 1 && ct.OFFSET16 == 1000, "CT range gave factor %f offset %f", ct.valueFactor, ct.OFFSET16);

    // 4D: the range of all times is 50..270, the second time is uniform 150
    View *four = [[View alloc] initWithMin:50 max:270 times:3 width:4 voxels:16];
    [four computeValueFactor];
    CHECK(four.valueFactor == 1 && four.OFFSET16 == -50, "4D range gave factor %f offset %f", four.valueFactor, four.OFFSET16);
    for (int i = 0; i < 16; i++) samples[i] = 150;
    [four convert:samples count:16];
    [four applyMovieRangeGuardTo16BitVolume];
    CHECK(four.volume16[4] == 0, "guard low voxel must be the encoded minimum (0), got %u", four.volume16[4]);
    CHECK(four.volume16[5] == 220, "guard high voxel must be the encoded maximum (220), got %u", four.volume16[5]);
    CHECK(four.volume16[6] == 100, "the data next to the guard must be untouched, got %u", four.volume16[6]);
    unsigned short lo = 65535, hi = 0;
    for (int i = 0; i < 16; i++) { if (four.volume16[i] < lo) lo = four.volume16[i]; if (four.volume16[i] > hi) hi = four.volume16[i]; }
    CHECK(lo == 0 && hi == 220, "every time must expose the 4D range 0..220 to VTK, got %u..%u", lo, hi);

    // a volume too small for the guard is left alone
    View *tiny = [[View alloc] initWithMin:50 max:270 times:3 width:4 voxels:4];
    [tiny computeValueFactor];
    [tiny applyMovieRangeGuardTo16BitVolume];
    CHECK(tiny.volume16[0] == 0 && tiny.volume16[3] == 0, "a one-row volume must not be written past its end");
    return 0;
} }
'''

if not failures:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / 'driver.mm'
        source.write_text(DRIVER)
        binary = Path(tmp) / 'driver'
        build = subprocess.run(['xcrun', 'clang++', '-fobjc-arc', '-framework', 'Foundation', '-framework', 'Accelerate',
                                str(source), '-o', str(binary)], capture_output=True, text=True)
        if build.returncode != 0:
            failures.append('driver did not compile:\n' + build.stderr[-3000:])
        else:
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            if run.returncode != 0:
                failures.append(run.stderr.strip() or 'driver failed without output')

if failures:
    for failure in failures:
        print('FAIL:', failure)
    raise SystemExit(1)
print('ok: VRView keeps one affine value map and guards the 4D range on every time')
