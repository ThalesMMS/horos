#!/usr/bin/env python3
"""Time the host's 3D renderer and the Metal renderer on the same state (#375, stage B of #210).

For the visible VRController: `--iterations` calls of `-[VRView render]` (the
VTK ray cast the host uses) timed on the main thread with mach_absolute_time,
then the same number of Metal renders of the current state at the view's
drawable size through the bridge, plus one first-frame time for each, and the
process footprint before and after. Both run in the same process, on the same
volume, camera, transfer function and size; VTK's own image-sample distance
(LOD) is reported because it decides how many rays it casts. No gain is
presumed and none is claimed.

    python3 tools/measure-native-volume-metal.py phantom --pid 123 --iterations 20
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('label')
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--iterations', type=int, default=20)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-375-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label) or not 1 <= args.iterations <= 200:
    parser.error('Use a positive PID, a lowercase label and 1-200 iterations')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / (args.label + '-timing.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')

expression = r'''
id f375C = nil;
for (NSWindow *f375W in (id)[(NSApplication*)NSApp windows]) {
  id wc = (id)[f375W windowController];
  if (wc && (BOOL)[wc isKindOfClass:(Class)objc_getClass("VRController")] && (BOOL)[f375W isVisible] && ![(NSString *)[wc style] isEqualToString:@"noNib"]) { f375C = wc; break; }
}
NSMutableDictionary *f375R = [NSMutableDictionary dictionary];
if (f375C) {
id f375V = (id)[f375C view];
mach_timebase_info_data_t f375TB; (void)mach_timebase_info(&f375TB);
struct task_vm_info f375Info; mach_msg_type_number_t f375Count = TASK_VM_INFO_COUNT;
(void)task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&f375Info, &f375Count);
f375R[@"footprintBefore"] = @((unsigned long long)f375Info.phys_footprint);
NSRect f375B = [(NSView *)f375V convertRectToBacking:[(NSView *)f375V bounds]];
long f375W = (long)f375B.size.width, f375H = (long)f375B.size.height;
f375R[@"width"] = @(f375W); f375R[@"height"] = @(f375H);
f375R[@"renderingMode"] = @((long)[f375V renderingMode]);
f375R[@"lod"] = @((float)[f375V lodDisplayed]);
f375R[@"shading"] = @((long)[f375V shading]);
NSMutableArray *f375VTK = [NSMutableArray array];
for (int f375I = 0; f375I < ITERATIONS; ++f375I) {
  uint64_t t0 = mach_absolute_time(); (void)[f375V render]; uint64_t t1 = mach_absolute_time();
  (void)[f375VTK addObject:@((double)(t1 - t0) * f375TB.numer / f375TB.denom / 1e6)];
}
f375R[@"vtkMilliseconds"] = f375VTK;
(void)[f375C horosVolumeMetalRelease];
uint64_t f0 = mach_absolute_time();
NSError *f375E = nil;
NSData *f375First = (NSData *)[f375C horosVolumeMetalRenderWithWidth:f375W height:f375H scalarOut:nil error:&f375E];
uint64_t f1 = mach_absolute_time();
f375R[@"metalFirstFrameMilliseconds"] = @((double)(f1 - f0) * f375TB.numer / f375TB.denom / 1e6);
f375R[@"metalFirstFrameBytes"] = @((long)[f375First length]);
NSMutableArray *f375Metal = [NSMutableArray array]; NSMutableArray *f375GPU = [NSMutableArray array];
for (int f375I = 0; f375I < ITERATIONS; ++f375I) {
  uint64_t t0 = mach_absolute_time(); NSData *d = (NSData *)[f375C horosVolumeMetalRenderWithWidth:f375W height:f375H scalarOut:nil error:&f375E]; uint64_t t1 = mach_absolute_time();
  (void)[f375Metal addObject:@((double)(t1 - t0) * f375TB.numer / f375TB.denom / 1e6)];
  (void)[f375GPU addObject:@((double)[f375C horosVolumeMetalLastMilliseconds])];
  (void)[d length];
}
f375R[@"metalMilliseconds"] = f375Metal; f375R[@"metalGPUMilliseconds"] = f375GPU;
f375R[@"metalVolumeBytes"] = @((long)[f375C horosVolumeMetalBytes]);
f375R[@"fallback"] = (NSString *)[f375C horosVolumeMetalFallbackReason] ?: @"";
(void)task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&f375Info, &f375Count);
f375R[@"footprintAfter"] = @((unsigned long long)f375Info.phys_footprint);
}
(void)[[NSJSONSerialization dataWithJSONObject:f375R options:3 error:nil] writeToFile:OUTPUT atomically:YES];
'''.replace('ITERATIONS', str(args.iterations)).replace('OUTPUT', '@' + json.dumps(str(staged)))
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
if 'vtkMilliseconds' not in state:
    raise SystemExit('no visible VRController')


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


summary = {'label': args.label, 'iterations': args.iterations, 'size': [state['width'], state['height']],
           'renderingMode': state['renderingMode'], 'lod': state['lod'], 'shading': state['shading'],
           'vtk': {'p50': percentile(state['vtkMilliseconds'], 0.5), 'p95': percentile(state['vtkMilliseconds'], 0.95)},
           'metal': {'firstFrame': state['metalFirstFrameMilliseconds'], 'p50': percentile(state['metalMilliseconds'], 0.5),
                     'p95': percentile(state['metalMilliseconds'], 0.95), 'gpuP50': percentile(state['metalGPUMilliseconds'], 0.5),
                     'volumeBytes': state['metalVolumeBytes'], 'fallback': state['fallback']},
           'footprintBefore': state['footprintBefore'], 'footprintAfter': state['footprintAfter']}
(args.output / (args.label + '-timing-summary.json')).write_text(json.dumps(summary, indent=1) + '\n')
print('%s %dx%d mode %d lod %.1f shading %d: VTK render p50 %.1f ms p95 %.1f ms | Metal first frame %.1f ms (upload + render), p50 %.1f ms p95 %.1f ms (GPU p50 %.1f ms) | footprint %.0f -> %.0f MB, volume %d bytes%s'
      % (args.label, state['width'], state['height'], state['renderingMode'], state['lod'], state['shading'],
         summary['vtk']['p50'], summary['vtk']['p95'], summary['metal']['firstFrame'], summary['metal']['p50'], summary['metal']['p95'],
         summary['metal']['gpuP50'], state['footprintBefore'] / 1048576, state['footprintAfter'] / 1048576, state['metalVolumeBytes'],
         (' fallback: ' + state['fallback']) if state['fallback'] else ''))
