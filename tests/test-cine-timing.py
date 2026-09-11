#!/usr/bin/env python3
"""Exercise production cine callbacks with a synthetic monotonic clock and a civil-clock jump.

Cadence steps a fake systemUptime so suite load cannot starve the production
zero-interval NSTimer. A real run-loop timer still checks that playback
continues across a civil-clock rollback.

This isolates scheduling from DICOM decoding, GPU rendering and synchronization.
"""
from pathlib import Path
import math
import re
import subprocess
import tempfile

# Same 3.2 s window as the original wall-clock run. The bound is still one
# missed or extra frame around elapsed*rate — not extra wall-clock slack.
# A loaded machine no longer changes the count, because time is simulated.
# Selecting 20/s and getting ~1/s or ~5/s still fails.
SIMULATED_SECONDS = 3.2


def cadence_ok(count, elapsed, selected):
    expected = elapsed * selected
    return math.floor(expected) - 1 <= count <= math.ceil(expected)


# Hand-checked literals for the 3.2 s window. 63 at 20/s is one missed frame
# (the original bound). 16 or 3 at 20/s is a truly wrong cadence.
assert cadence_ok(3, 3.2, 1) and cadence_ok(16, 3.2, 5) and cadence_ok(64, 3.2, 20)
assert cadence_ok(63, 3.2, 20)
assert not cadence_ok(62, 3.2, 20)
assert not cadence_ok(16, 3.2, 20) and not cadence_ok(3, 3.2, 20)
assert not cadence_ok(3, 3.2, 5)

root = Path(__file__).resolve().parents[1]
source = (root / 'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
def method(start, end):
    return source[source.index(start):source.index(end, source.index(start))]
uptime = '[NSProcessInfo processInfo].systemUptime'
callbacks = method('- (void) performMovieAnimation:', '- (long) imageIndex')
callbacks += method('- (void) performAnimation:', '- (void) MovieStop:')
if callbacks.count(uptime) < 2:
    raise SystemExit(f'expected systemUptime in cine callbacks, found {callbacks.count(uptime)}')
callbacks = callbacks.replace(uptime, 'testUptime()')
phase_start = method('- (void) MoviePlayStop:', '- (BOOL)isPlaying4D')
slice_start = method('- (void) PlayStop:', '#pragma mark 4.4.2 4D navigation')
initializers = '\n'.join('v->' + re.search(r'\b' + field + r' = .*?;', body).group(0)
                         for field, body in [('lastTime', slice_start), ('lastTimeFrame', slice_start), ('lastMovieTime', phase_start)])
initializers = initializers.replace(uptime, 'testUptime()')
if 'systemUptime' in callbacks or 'systemUptime' in initializers:
    raise SystemExit('missed a systemUptime substitution')
code = r'''
#import <AppKit/AppKit.h>
#include <math.h>
#include <stdio.h>
static double clockOffset;
static double testClock;
static BOOL useTestClock;
static double testUptime(void) {
 return useTestClock ? testClock : NSProcessInfo.processInfo.systemUptime;
}
@interface TestWallClock : NSObject
+ (NSTimeInterval)timeIntervalSinceReferenceDate;
@end
@implementation TestWallClock
+ (NSTimeInterval)timeIntervalSinceReferenceDate { return NSDate.timeIntervalSinceReferenceDate + clockOffset; }
@end
#define NSDate TestWallClock
@interface HorosFourDSeriesGuard : NSObject
+ (NSInteger)nextIndex:(NSInteger)current count:(NSInteger)count;
@end
@implementation HorosFourDSeriesGuard
+ (NSInteger)nextIndex:(NSInteger)current count:(NSInteger)count {
 if (count <= 0) return 0;
 NSInteger remainder = (current + 1) % count;
 return remainder >= 0 ? remainder : remainder + count;
}
@end
@interface ImageProbe : NSObject
@property short curImage;
@property BOOL flippedData;
- (void)setIndex:(short)index;
- (void)sendSyncMessage:(int)value;
- (void)displayIfNeeded;
@end
@implementation ImageProbe
- (void)setIndex:(short)index { self.curImage=index; }
- (void)sendSyncMessage:(int)value {}
- (void)displayIfNeeded {}
@end
@interface ViewerController : NSObject {
@public
 NSThread *loadingThread;
 NSTimeInterval lastTime, lastMovieTime, lastTimeFrame;
 NSSlider *speedSlider, *movieRateSlider;
 NSTextField *speedText;
 NSButton *loopButton;
 ImageProbe *imageView;
 NSArray *pixList[1];
 short curMovieIndex, maxMovieIndex, direction;
 BOOL windowWillClose;
 int speedometer, sliceCount, phaseCount;
}
- (void)setMovieIndex:(short)value;
- (void)propagateSettings;
- (void)adjustSlider;
@end
@implementation ViewerController
- (id)init { if ((self=[super init])) {
 speedSlider=[NSSlider new]; speedSlider.maxValue=60;
 movieRateSlider=[NSSlider new]; movieRateSlider.maxValue=60;
 speedText=[NSTextField new]; loopButton=[NSButton new]; loopButton.state=NSOnState;
 imageView=[ImageProbe new]; pixList[0]=@[@0,@1,@2]; direction=1; maxMovieIndex=3;
 } return self; }
- (void)setMovieIndex:(short)value { phaseCount++; }
- (void)propagateSettings {}
- (void)adjustSlider { sliceCount++; }
CALLBACKS
@end
static void runFor(double duration) {
 double end=NSProcessInfo.processInfo.systemUptime+duration;
 while (NSProcessInfo.processInfo.systemUptime < end)
  [NSRunLoop.currentRunLoop runMode:NSDefaultRunLoopMode beforeDate:[(id)NSClassFromString(@"NSDate") dateWithTimeIntervalSinceNow:0.01]];
}
int main(void) { @autoreleasepool {
 [NSApplication sharedApplication];
 if (!(floor(3.2*20)-1 <= 63 && 63 <= ceil(3.2*20))) return 1;
 if (floor(3.2*20)-1 <= 16 && 16 <= ceil(3.2*20)) return 1;
 for (int mode=0; mode<2; mode++) {
  for (NSNumber *rate in @[@1,@5,@20]) {
   ViewerController *v=[ViewerController new];
   v->speedSlider.floatValue=rate.floatValue; v->movieRateSlider.floatValue=rate.floatValue;
   useTestClock=YES; testClock=1000;
   INITIALIZERS
   const double step=0.0001;
   const int ticks=(int)llround(3.2/step);
   for (int i=0;i<ticks;i++) {
    testClock+=step;
    if (mode) [v performMovieAnimation:nil]; else [v performAnimation:nil];
   }
   int count=mode ? v->phaseCount : v->sliceCount;
   double elapsed=3.2;
   double expected=elapsed*rate.doubleValue;
   NSLog(@"%@ selected %@: %d advances / %.3f s simulated (%.3f/s)",mode ? @"phase" : @"slice",rate,count,elapsed,count/elapsed);
   if (!(count >= floor(expected)-1 && count <= ceil(expected))) {
    fprintf(stderr,"FAIL: count >= floor(expected)-1 && count <= ceil(expected) (%s %.0f : %d advances, expected %.3f, allow [%.0f, %.0f])\n",
      mode ? "phase" : "slice", rate.doubleValue, count, expected, floor(expected)-1, ceil(expected));
    return 1;
   }
   // An NTP/manual correction must not freeze cine until civil time catches up.
   useTestClock=NO;
   INITIALIZERS
   count=mode ? v->phaseCount : v->sliceCount;
   NSTimer *timer=[NSTimer scheduledTimerWithTimeInterval:0 target:v selector:mode ? @selector(performMovieAnimation:) : @selector(performAnimation:) userInfo:nil repeats:YES];
   clockOffset=-3600;
   runFor(1.2);
   int after=mode ? v->phaseCount : v->sliceCount;
   if (!(after > count)) {
    fprintf(stderr,"FAIL: after > count (%s %.0f : %d after civil-clock rollback, was %d)\n",
      mode ? "phase" : "slice", rate.doubleValue, after, count);
    return 1;
   }
   [timer invalidate]; clockOffset=0;
  }
 }
 NSLog(@"PASS: slice and phase cadence on simulated uptime, playback continues across civil-clock rollback");
} }
'''.replace('CALLBACKS', callbacks).replace('INITIALIZERS', initializers)
with tempfile.TemporaryDirectory(prefix='horos-cine-timing-') as directory:
    path = Path(directory)
    (path/'test.m').write_text(code)
    subprocess.run(['xcrun','clang','-fobjc-arc','-framework','AppKit',str(path/'test.m'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
