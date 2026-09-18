#!/usr/bin/env python3
"""Time VTK and Metal 3D MPR reconstruction in a running development Horos.

For the first MPRController, forces `--iterations` reconstructions of the first
view through the same call the host makes after a camera change
(`restoreCamera`, `camera.forceUpdate`, `updateViewMPR`) with Use Metal in MPR
off and then on, timing each call on the main thread with mach_absolute_time.
Reports p50/p95 per state, the Metal bridge wall time, GPU volume bytes and
process footprint. Three warm-up reconstructions precede each measured state.
This measures reconstruction, not input-to-display latency or FPS. The current
Metal route skips the CPU ray cast; historical builds ran both paths.

Since #620 each timed reconstruction drains its own autorelease pool, as the
app's event loop does after each frame: without it every frame's command buffer,
and the output plane it holds, lived until the whole loop ended, which is not
what the app does between frames.

    python3 tools/measure-native-mpr-metal.py ct-500 --pid 123 --iterations 30
"""
import argparse
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('label')
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--iterations', type=int, default=30)
parser.add_argument('--view', type=int, choices=(1, 2, 3), default=1)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-374-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label) or not 1 <= args.iterations <= 500:
    parser.error('Use a positive PID, a lowercase label and 1-500 iterations')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / (args.label + '-timing.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

expression = r'''
id m374C = nil;
for (NSWindow *m374W in (id)[(NSApplication*)NSApp windows]) {
  id m374Controller = (id)[m374W windowController];
  if (m374Controller && (BOOL)[m374Controller isKindOfClass:(Class)objc_getClass("MPRController")]) { m374C = m374Controller; break; }
}
if (m374C) {
mach_timebase_info_data_t m374TB; (void)mach_timebase_info(&m374TB);
NSMutableDictionary *m374R = [NSMutableDictionary dictionary];
id m374V = (id)[m374C mprViewVIEW];
BOOL m374InitialMetal = (BOOL)[m374C horosMPRMetalEnabled];
for (int m374State = 0; m374State < 2; ++m374State) {
  if ((BOOL)[m374C horosMPRMetalEnabled] != (BOOL)m374State) { (void)[m374C toggleMPRMetal:nil]; }
  for (int m374Warm = 0; m374Warm < 3; ++m374Warm) {
    (void)[m374V restoreCamera]; (void)[(id)[m374V camera] setForceUpdate:YES]; (void)[m374V updateViewMPR];
  }
  NSMutableArray *m374Times = [NSMutableArray array];
  NSMutableArray *m374GPU = [NSMutableArray array];
  for (int m374I = 0; m374I < ITERATIONS; ++m374I) {
    uint64_t m374T0 = mach_absolute_time();
    void *m374Pool = (void *)objc_autoreleasePoolPush();
    (void)[m374V restoreCamera]; (void)[(id)[m374V camera] setForceUpdate:YES]; (void)[m374V updateViewMPR];
    (void)objc_autoreleasePoolPop(m374Pool);
    uint64_t m374T1 = mach_absolute_time();
    (void)[m374Times addObject:@((double)(m374T1 - m374T0) * m374TB.numer / m374TB.denom / 1e6)];
    (void)[m374GPU addObject:@((double)[m374C horosMPRLastMilliseconds])];
  }
  struct task_vm_info m374Info; mach_msg_type_number_t m374Count = TASK_VM_INFO_COUNT;
  (void)task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&m374Info, &m374Count);
  m374R[m374State ? @"metal" : @"vtk"] = @{@"milliseconds": m374Times, @"gpuMilliseconds": m374GPU,
     @"footprintBytes": @((unsigned long long)m374Info.phys_footprint), @"volumeBytes": @((long)[m374C horosMPRVolumeBytes]),
     @"fallback": (id)[m374C horosMPRFallbackReason] ?: @""};
}
if ((BOOL)[m374C horosMPRMetalEnabled] != m374InitialMetal) { (void)[m374C toggleMPRMetal:nil]; }
id m374P = (id)[m374V pix];
m374R[@"plane"] = @{@"width": @((long)[m374P pwidth]), @"height": @((long)[m374P pheight]), @"thicknessMm": @((float)[m374C getClippingRangeThicknessInMm]), @"mode": @((int)[m374C clippingRangeMode])};
id m374O = (id)[m374C originalPix];
m374R[@"volume"] = @{@"width": @((long)[m374O pwidth]), @"height": @((long)[m374O pheight]),
  @"depth": @((long)[(NSArray*)[(id)[(NSArray*)[(id)objc_getClass("ViewerController") get2DViewers] firstObject] pixList] count])};
(void)[[NSJSONSerialization dataWithJSONObject:m374R options:3 error:nil] writeToFile:OUTPUT atomically:YES];
}
'''.replace('ITERATIONS', str(args.iterations)).replace('VIEW', str(args.view)).replace('OUTPUT', '@' + json.dumps(str(staged)))
commands = args.output / (args.label + '-timing.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- @import Darwin\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\n'
                    'process detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                        capture_output=True, text=True)
(args.output / (args.label + '-timing.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('Measurement failed; inspect the local LLDB log')
staged.replace(output)
state = json.loads(output.read_text())


def percentile(values, q):
    ordered = sorted(values)
    if q == 0.5:
        return statistics.median(ordered)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


summary = {'label': args.label, 'iterations': args.iterations, 'view': args.view, 'warmup': 3, 'plane': state['plane'], 'volume': state['volume']}
for key in ('vtk', 'metal'):
    times = state[key]['milliseconds']
    summary[key] = {'p50': percentile(times, 0.5), 'p95': percentile(times, 0.95), 'min': min(times), 'max': max(times),
                    'gpuP50': percentile(state[key]['gpuMilliseconds'], 0.5), 'gpuP95': percentile(state[key]['gpuMilliseconds'], 0.95),
                    'footprintBytes': state[key]['footprintBytes'], 'volumeBytes': state[key]['volumeBytes'], 'fallback': state[key]['fallback']}
    print('%s %-5s p50 %.2f ms p95 %.2f ms (Metal bridge wall p50 %.3f ms) footprint %.1f MB volume %d bytes%s' % (
        args.label, key, summary[key]['p50'], summary[key]['p95'], summary[key]['gpuP50'],
        summary[key]['footprintBytes'] / 1048576, summary[key]['volumeBytes'],
        (' fallback: ' + summary[key]['fallback']) if summary[key]['fallback'] else ''))
(args.output / (args.label + '-timing-summary.json')).write_text(json.dumps(summary, indent=1) + '\n')
