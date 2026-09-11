#!/usr/bin/env python3
"""Compare native CPU/Metal VR renders at the current camera in development Horos.

Attaches LLDB, warms each engine, measures NSView.display through the native VR
renderer, captures the native RGB readback, and restores the selected engine/LOD.
No input events are sent.
These are synchronous rendering times, not input latency or displayed FPS.
Run without Instruments or other GPU workloads; raw captures stay local.
"""
import argparse
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import uuid

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('label')
p.add_argument('--pid', required=True, type=int)
p.add_argument('--iterations', type=int, default=20)
p.add_argument('--output', type=Path, default=Path('local-validation/vr-metal'))
a = p.parse_args()
if a.pid <= 0 or not re.fullmatch('[a-z0-9-]+', a.label) or not 1 <= a.iterations <= 100:
    p.error('Use a positive PID, lowercase label and 1-100 iterations')
a.output.mkdir(parents=True, exist_ok=True)
base = (a.output / a.label).resolve()
staged = Path(str(base) + '.' + uuid.uuid4().hex + '.partial')
expression = r'''
id vrBenchController = nil;
for (NSWindow *vrBenchWindow in (NSArray *)[(NSApplication *)NSApp windows]) {
 id vrBenchCandidate = (id)[vrBenchWindow windowController];
 if ((BOOL)[vrBenchWindow isVisible] && (BOOL)[vrBenchCandidate isKindOfClass:(Class)objc_getClass("VRController")] && ![(NSString *)[vrBenchCandidate style] isEqualToString:@"noNib"]) { vrBenchController = vrBenchCandidate; break; }
}
if (vrBenchController) {
 id vrBenchView = (id)[vrBenchController view];
 int vrBenchInitialEngine = [(NSNumber *)[(NSObject *)vrBenchView valueForKey:@"engine"] intValue];
 float vrBenchInitialLOD = [(NSNumber *)[(NSObject *)vrBenchView valueForKey:@"LOD"] floatValue];
 mach_timebase_info_data_t vrBenchTimebase; (void)mach_timebase_info(&vrBenchTimebase);
 NSMutableDictionary *vrBenchResult = [NSMutableDictionary dictionary];
 for (NSNumber *vrBenchEngine in @[@0, @2, @0, @2]) {
  @autoreleasepool {
   (void)[vrBenchView setEngine:(long)[vrBenchEngine longValue] showWait:(BOOL)0];
   [(NSObject *)vrBenchView setValue:@2 forKey:@"LOD"];
   for (int vrBenchWarm=0;vrBenchWarm<3;++vrBenchWarm) [(NSView *)vrBenchView display];
   NSMutableArray *vrBenchTimes=[NSMutableArray array], *vrBenchGPU=[NSMutableArray array];
   for (int vrBenchIteration=0;vrBenchIteration<ITERATIONS;++vrBenchIteration) {
    uint64_t vrBenchStart=mach_absolute_time(); [(NSView *)vrBenchView display];
    [vrBenchTimes addObject:@((mach_absolute_time()-vrBenchStart)*(double)vrBenchTimebase.numer/vrBenchTimebase.denom/1e6)];
    [vrBenchGPU addObject:@((double)[vrBenchController horosVolumeMetalLastMilliseconds])];
   }
   NSMutableDictionary *vrBenchSnapshot = [(NSDictionary *)[vrBenchController horosVolumeSnapshot] mutableCopy];
   [vrBenchSnapshot removeObjectForKey:@"volume"]; [vrBenchSnapshot removeObjectForKey:@"clut"];
   long vrBenchWidth=0,vrBenchHeight=0,vrBenchSamples=0,vrBenchBits=0;
   unsigned char *vrBenchPixels=(unsigned char *)[vrBenchView getRawPixels:&vrBenchWidth :&vrBenchHeight :&vrBenchSamples :&vrBenchBits :(BOOL)0 :(BOOL)0];
   NSString *vrBenchKey=[NSString stringWithFormat:@"engine%@-pass%lu",vrBenchEngine,(unsigned long)[vrBenchResult count]];
   if(vrBenchPixels) { (void)[[NSData dataWithBytes:vrBenchPixels length:(NSUInteger)(vrBenchWidth*vrBenchHeight*vrBenchSamples*vrBenchBits/8)] writeToFile:[NSString stringWithFormat:@"%@-%@.rgb",BASE,vrBenchKey] atomically:YES]; free(vrBenchPixels); }
   NSRect vrBenchBounds=[(NSView *)vrBenchView bounds];
   NSRect vrBenchBacking=[(NSView *)vrBenchView convertRectToBacking:vrBenchBounds];
   vrBenchResult[vrBenchKey]=@{@"milliseconds":vrBenchTimes,@"metalBridgeMilliseconds":vrBenchGPU,@"snapshot":vrBenchSnapshot,
    @"initialEngine":@(vrBenchInitialEngine),@"initialLOD":@(vrBenchInitialLOD),
    @"engine":[(NSObject *)vrBenchView valueForKey:@"engine"],@"LOD":[(NSObject *)vrBenchView valueForKey:@"LOD"],
    @"width":@(vrBenchWidth),@"height":@(vrBenchHeight),@"samples":@(vrBenchSamples),@"bits":@(vrBenchBits),
    @"bounds":@[@(vrBenchBounds.size.width),@(vrBenchBounds.size.height)],@"backing":@[@(vrBenchBacking.size.width),@(vrBenchBacking.size.height)],
    @"fallback":(NSString *)[vrBenchController horosVolumeMetalFallbackReason]?:@"",@"volumeBytes":@((long)[vrBenchController horosVolumeMetalBytes])};
  }
 }
 (void)[vrBenchView setEngine:(long)vrBenchInitialEngine showWait:(BOOL)0];
 [(NSObject *)vrBenchView setValue:@(vrBenchInitialLOD) forKey:@"LOD"];
 [(NSView *)vrBenchView setNeedsDisplay:YES];
 (void)[[NSJSONSerialization dataWithJSONObject:vrBenchResult options:3 error:nil] writeToFile:OUTPUT atomically:YES];
}
'''.replace('ITERATIONS', str(a.iterations)).replace('BASE', '@'+json.dumps(str(base))).replace('OUTPUT', '@'+json.dumps(str(staged)))
commands = Path(str(base)+'.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\nexpression -l objc++ -- @import Darwin\n'
                   'expression -l objc++ -- { '+ ' '.join(expression.splitlines())+' }\nprocess detach\n')
r = subprocess.run(['xcrun','lldb','--batch','-p',str(a.pid),'-s',str(commands)],capture_output=True,text=True)
Path(str(base)+'.log').write_text(r.stdout+r.stderr)
if r.returncode or not staged.exists():
    raise SystemExit('Measurement failed; inspect '+str(base)+'.log')
output=Path(str(base)+'.json');staged.replace(output)
for name,run in json.loads(output.read_text()).items():
    values=sorted(run['milliseconds']);run['p50']=statistics.median(values);run['p95']=values[math.ceil(len(values)*.95)-1]
    print('%s: p50 %.2f ms, p95 %.2f ms, %dx%d, fallback=%r' % (name,run['p50'],run['p95'],run['width'],run['height'],run['fallback']))
print(output)
