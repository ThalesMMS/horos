#!/usr/bin/env python3
"""Time the planar host path on both Metal backends, inside the app (#609).

Each step is one LLDB attach to a `--debug` development build. The measurement
drives the real `DCMView` draw - snapshot, Metal submission, IOSurface handover
and the OpenGL composition with overlays - not a microbenchmark of submission.

    python3 tools/exercise-native-planar-backend.py state     --pid P
    python3 tools/exercise-native-planar-backend.py configure --pid P --pilot YES
    python3 tools/exercise-native-planar-backend.py measure   --pid P --frames 120 --label metal4

`configure` writes the pilot preference, drops any renderer built under the old
one and turns the viewer's planar Metal presentation on, so the next draw builds
the backend that was asked for. `measure` scrolls one frame at a time and times
the complete draw. Snapshots are JSON under local-validation; no pixels, names
or identifiers leave the process.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['state', 'configure', 'measure'])
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--pilot', choices=['YES', 'NO'], default='NO')
parser.add_argument('--frames', type=int, default=120)
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-609-native'))
arguments = parser.parse_args()

label = arguments.label or arguments.step
if not re.fullmatch('[a-z0-9-]+', label):
    parser.error('Use a lowercase label')
arguments.output.mkdir(parents=True, exist_ok=True)
output = (arguments.output / ('planar-' + label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

COMMON = r'''
NSMutableDictionary *m609 = [NSMutableDictionary dictionary];
id vc609 = (id)[(NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers] firstObject];
id view609 = vc609 ? (id)[(id)vc609 imageView] : nil;
m609[@"hasViewer"] = @(vc609 != nil);
'''

STATE = r'''
if (view609) {
  m609[@"planarEnabled"] = @((BOOL)[(id)vc609 horosPlanarMetalEnabled]);
  m609[@"fallbackReason"] = (NSString*)[(id)view609 horosPlanarFallbackReason] ?: @"";
  m609[@"backend"] = (NSString*)[(id)view609 horosPlanarBackendName] ?: @"";
  m609[@"lastGPUMilliseconds"] = @((double)[(id)view609 horosPlanarGPUMilliseconds]);
  m609[@"curImage"] = @((long)[(id)view609 curImage]);
  m609[@"imageCount"] = @((long)[(NSArray*)[(id)view609 dcmPixList] count]);
}
m609[@"pilotPreference"] = @((BOOL)[[NSUserDefaults standardUserDefaults] boolForKey: @"HorosPlanarMetal4Pilot"]);
'''

if arguments.step == 'state':
    body = COMMON + STATE

elif arguments.step == 'configure':
    body = COMMON + r'''
[[NSUserDefaults standardUserDefaults] setBool: PILOT forKey: @"HorosPlanarMetal4Pilot"];
if (vc609) {
  for (id v609 in (NSArray*)[(id)vc609 imageViews]) {
    (void)[(id)v609 horosInvalidatePlanar];
  }
  if ((BOOL)[(id)vc609 horosPlanarMetalEnabled] == NO)
    (void)[(id)vc609 togglePlanarMetal: nil];
  for (id v609 in (NSArray*)[(id)vc609 imageViews]) {
    (void)[(id)v609 setNeedsDisplay: YES];
    (void)[(id)v609 display];
  }
}
'''.replace('PILOT', arguments.pilot) + STATE

elif arguments.step == 'measure':
    body = COMMON + r'''
NSMutableArray *times609 = [NSMutableArray array];
NSMutableArray *gpu609 = [NSMutableArray array];
long frames609 = FRAMES;
if (view609) {
  long count609 = (long)[(NSArray*)[(id)view609 dcmPixList] count];
  if (count609 < 1) count609 = 1;
  for (long i609 = 0; i609 < frames609; i609++) {
    (void)[(id)view609 setIndex: (short)(i609 % count609)];
    (void)[(id)view609 setNeedsDisplay: YES];
    CFTimeInterval start609 = CACurrentMediaTime();
    (void)[(id)view609 display];
    CFTimeInterval end609 = CACurrentMediaTime();
    if (i609 >= 20) {
      (void)[times609 addObject: @((end609 - start609) * 1000.0)];
      (void)[gpu609 addObject: @((double)[(id)view609 horosPlanarGPUMilliseconds])];
    }
  }
  m609[@"fallbackReason"] = (NSString*)[(id)view609 horosPlanarFallbackReason] ?: @"";
  m609[@"planarEnabled"] = @((BOOL)[(id)vc609 horosPlanarMetalEnabled]);
  m609[@"backend"] = (NSString*)[(id)view609 horosPlanarBackendName] ?: @"";
}
m609[@"drawMilliseconds"] = times609;
m609[@"gpuMilliseconds"] = gpu609;
m609[@"frames"] = @(frames609);
m609[@"pilotPreference"] = @((BOOL)[[NSUserDefaults standardUserDefaults] boolForKey: @"HorosPlanarMetal4Pilot"]);
'''.replace('FRAMES', str(arguments.frames))

expr = body + '(void)[[NSJSONSerialization dataWithJSONObject:m609 options:3 error:nil] writeToFile:@"STAGED" atomically:YES];\n'
expr = expr.replace('STAGED', str(staged))
commands = arguments.output / ('planar-' + label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- @import QuartzCore\n'
                    'expression -l objc++ -- { ' + ' '.join(expr.splitlines()) + ' }\nprocess detach\n')
run = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(arguments.pid), '-s', str(commands)],
                     capture_output=True, text=True)
(arguments.output / ('planar-' + label + '.log')).write_text(run.stdout + run.stderr)
if not staged.exists():
    print(run.stdout[-3000:])
    print(run.stderr[-2000:])
    raise SystemExit('the step produced no snapshot; see %s' % (arguments.output / ('planar-' + label + '.log')))
staged.replace(output)
record = json.loads(output.read_text())
times = record.get('drawMilliseconds') or []
if times:
    ordered = sorted(times)
    gpu = sorted(v for v in (record.get('gpuMilliseconds') or []) if v > 0)
    record['summary'] = {
        'gpuSamples': len(gpu),
        'gpuMedian': gpu[len(gpu) // 2] if gpu else None,
        'samples': len(ordered),
        'median': ordered[len(ordered) // 2],
        'p95': ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)],
        'mean': sum(ordered) / len(ordered),
        'min': ordered[0], 'max': ordered[-1],
    }
    output.write_text(json.dumps(record, indent=1) + '\n')
print(output)
print(json.dumps({k: v for k, v in record.items() if k not in ('drawMilliseconds', 'gpuMilliseconds')}, indent=1))
