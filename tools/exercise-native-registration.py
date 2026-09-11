#!/usr/bin/env python3
"""Drive the guided ROI copy between two open viewers of the registration fixture (#378, A237).

Attaches lldb to the dev build (native harness) and, on the two viewers of
patient SYNTHETIC-378 ("Registration fixed" = target A, "Registration moving"
= source B, related by the manifest's transform T), runs one subcommand per
call and writes `<label>.json` under `local-validation/issue-378-native/`:

    landmarks   2D point ROIs L1..L4 at the marker voxel centres on both viewers
    clear       remove every ROI from both viewers
    rois        polygons on B slices 4, 7, 10 and a rectangle on slice 12
    fuse        [A ActivateBlending:B]: the Fusion dialog's product
    plan        A's guided copy plan from B (quality, algorithm, placements)
    apply       plan + apply under one undo entry
    dump        every ROI of A and B: slice, name, type, points/rect, comments
    undo        [A undo:nil]
    rename      rename L4 on B to X (refusal path) / restore
    blend       move the Fusion panel's blend slider to 25 % of its range through the host action; report the session blend and every pane's blending factor
    comparison  pending-comparison text between A and the other open viewer, then confirm and re-check

    python3 tools/exercise-native-registration.py --pid N landmarks
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--fixture', type=Path, default=Path('../DICOM_Example/local-validation/issue-378-registration-2026-09-13'))
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-378-native'))
parser.add_argument('--label')
parser.add_argument('command', choices=['clear', 'landmarks', 'rois', 'fuse', 'plan', 'apply', 'dump', 'undo', 'rename', 'restore', 'comparison', 'blend'])
args = parser.parse_args()
label = args.label or args.command
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', label):
    parser.error('positive PID and a lowercase label')
manifest = json.loads((args.fixture / 'manifest.json').read_text())
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')


def s(value):
    return '@' + json.dumps(str(value))


preamble = r'''
id r378A = nil; id r378B = nil; id r378Other = nil;
for (id c in (NSArray*)[(id)objc_getClass("ViewerController") get2DViewers]) {
  NSString *desc378 = (NSString*)[(NSObject*)[c currentSeries] valueForKey:@"name"];
  NSString *pid378 = (NSString*)[(NSObject*)[c currentStudy] valueForKey:@"patientID"];
  if ([pid378 isEqualToString:@"SYNTHETIC-378"] && [desc378 isEqualToString:@"Registration fixed"]) r378A = c;
  else if ([pid378 isEqualToString:@"SYNTHETIC-378"] && [desc378 isEqualToString:@"Registration moving"]) r378B = c;
  else r378Other = c;
}
NSMutableDictionary *r378R = [NSMutableDictionary dictionary];
r378R[@"fixedViewer"] = @(r378A != nil); r378R[@"movingViewer"] = @(r378B != nil); r378R[@"otherViewer"] = @(r378Other != nil);
r378R[@"fused"] = @(r378A && (id)[r378A blendingController] == r378B);
'''

# Adds one ROI to a viewer's slice: type 19 = 2D point (rect origin), 11 = closed polygon (points).
add_roi = r'''
{ id v378 = VIEWER; long k378 = SLICE; id pix378 = (id)[(NSArray*)[v378 pixList:0] objectAtIndex:k378];
  NSPoint o378 = (NSPoint)[(Class)objc_getClass("DCMPix") originCorrectedAccordingToOrientation:pix378];
  id roi378 = (id)[(id)[(Class)objc_getClass("ROI") alloc] initWithType:(long)TYPE :(float)(double)[pix378 pixelSpacingX] :(float)(double)[pix378 pixelSpacingY] :o378];
  (void)[roi378 setName:NAME];
  BODY
  (void)[roi378 setPix:pix378];
  (void)[(NSMutableArray*)[(NSArray*)[v378 roiList:0] objectAtIndex:k378] addObject:roi378];
  (void)[(id)[v378 imageView] roiSet:roi378];
  [[NSNotificationCenter defaultCenter] postNotificationName:@"OsirixAddROINotification" object:v378 userInfo:@{@"ROI": roi378, @"sliceNumber": @(k378)}];
}
'''


def point_roi(viewer, slice_index, name, x, y, width=0, height=0, type_code=19):
    body = 'NSRect rr378; rr378.origin.x = %r; rr378.origin.y = %r; rr378.size.width = %r; rr378.size.height = %r; (void)[roi378 setROIRect:rr378];' % (float(x), float(y), float(width), float(height))
    return add_roi.replace('VIEWER', viewer).replace('SLICE', str(slice_index)).replace('TYPE', str(type_code)).replace('NAME', s(name)).replace('BODY', body)


def polygon_roi(viewer, slice_index, name, points):
    items = ', '.join('(id)[(Class)objc_getClass("MyPoint") point:(NSPoint){%r, %r}]' % (float(x), float(y)) for x, y in points)
    body = '(void)[roi378 setPoints:[NSMutableArray arrayWithArray:@[%s]]];' % items
    return add_roi.replace('VIEWER', viewer).replace('SLICE', str(slice_index)).replace('TYPE', '11').replace('NAME', s(name)).replace('BODY', body)


dump = r'''
NSMutableDictionary *r378D = [NSMutableDictionary dictionary];
for (NSString *key378 in @[@"A", @"B"]) {
  id v378 = [key378 isEqualToString:@"A"] ? r378A : r378B; if (!v378) continue;
  NSMutableArray *list378 = [NSMutableArray array];
  NSArray *slices378 = (NSArray*)[v378 roiList:0];
  for (long k378 = 0; k378 < (long)[slices378 count]; k378++) {
    for (id roi378 in (NSArray*)[slices378 objectAtIndex:k378]) {
      NSMutableArray *pts378 = [NSMutableArray array];
      for (id p378 in (NSArray*)[roi378 points]) { NSPoint pp378 = (NSPoint)[p378 point]; (void)[pts378 addObject:@[@((double)pp378.x), @((double)pp378.y)]]; }
      NSRect rc378 = (NSRect)[roi378 rect];
      (void)[list378 addObject:@{@"slice": @(k378), @"name": (NSString*)[roi378 name] ?: @"", @"type": @((long)[roi378 type]), @"points": pts378,
        @"rect": @[@((double)rc378.origin.x), @((double)rc378.origin.y), @((double)rc378.size.width), @((double)rc378.size.height)],
        @"comments": (NSString*)[roi378 comments] ?: @""}];
    }
  }
  r378D[key378] = list378;
}
r378R[@"rois"] = r378D;
'''

body = ''
if args.command == 'clear':
    body = r'''
for (id v378 in @[r378A ?: [NSNull null], r378B ?: [NSNull null]]) { if ((id)v378 == (id)[NSNull null]) continue;
  for (NSMutableArray *sl378 in (NSArray*)[v378 roiList:0]) (void)[sl378 removeAllObjects];
  (void)[(id)[v378 imageView] setIndex:(short)(long)[(id)[v378 imageView] curImage]]; (void)[(NSView*)[v378 imageView] setNeedsDisplay:YES]; }
''' + dump
elif args.command == 'landmarks':
    for index, (cx, cy, cz) in enumerate(manifest['markersColumnRowSlice']):
        for viewer in ('r378A', 'r378B'):
            body += 'if (%s) ' % viewer + point_roi(viewer, cz, 'L%d' % (index + 1), cx + 0.5, cy + 0.5)
    body += dump
elif args.command == 'rois':
    polygons = {4: [(6, 6), (14, 6), (14, 12), (6, 12)], 7: [(18, 5), (28, 9), (22, 15)], 10: [(5, 20), (12, 26), (4, 28)]}
    for k, pts in polygons.items():
        body += 'if (r378B) ' + polygon_roi('r378B', k, 'Poly%d' % k, pts)
    body += 'if (r378B) ' + point_roi('r378B', 12, 'Rect12', 20, 21, 4, 4, type_code=6)
    body += dump
elif args.command == 'fuse':
    # ActivateBlending: raises the host's "2D Planes" panel when the planes are not parallel; run it after
    # this expression returns so the panel can be answered ("Fusion", keeping B's own geometry).
    body = 'if (r378A && r378B) { id a378 = r378A, b378 = r378B; (void)[a378 performSelector:@selector(ActivateBlending:) withObject:b378 afterDelay:0.2]; r378R[@"scheduled"] = @YES; }\n'
elif args.command in ('plan', 'apply'):
    body = r'''
if (r378A && r378B) {
  NSString *refusal378 = nil;
  id plan378 = (id)[r378A horosGuidedCopyPlanFromViewer:r378B offsetMM:@[@0, @0, @0] refusal:&refusal378];
  r378R[@"refusal"] = refusal378 ?: @"";
  if (plan378) {
    r378R[@"summary"] = (NSString*)[plan378 summary];
    r378R[@"placed"] = @((long)[(NSArray*)[plan378 placed] count]);
    r378R[@"refused"] = @((long)[(NSArray*)[plan378 refused] count]);
    r378R[@"algorithm"] = (NSString*)[(id)[plan378 transform] algorithm];
    r378R[@"version"] = (NSString*)[(id)[plan378 transform] version];
    r378R[@"rowMajor"] = (NSArray*)[(id)[plan378 transform] rowMajor];
    NSMutableArray *pl378 = [NSMutableArray array];
    for (id p378 in (NSArray*)[plan378 placements]) {
      NSRect rc378 = (NSRect)[p378 rect];
      (void)[pl378 addObject:@{@"name": (NSString*)[p378 name], @"sourceSlice": @((long)[p378 sourceImageIndex]), @"targetSlice": @((long)[p378 targetImageIndex]),
        @"status": @((long)[p378 status]), @"reason": (NSString*)[p378 reason], @"through": @((double)[p378 throughPlaneMM]),
        @"points": (NSArray*)[p378 points], @"rect": @[@((double)rc378.origin.x), @((double)rc378.origin.y)], @"patient": (NSArray*)[p378 patientPoints]}];
    }
    r378R[@"placements"] = pl378;
  }
  id session378 = (id)[r378A horosRegistrationSession];
  NSMutableArray *comp378 = [NSMutableArray array];
  for (id c378 in (NSArray*)[session378 companions]) {
    id q378 = (id)[c378 quality];
    (void)[comp378 addObject:@{@"series": (NSString*)[c378 seriesInstanceUID], @"aligned": @((BOOL)[c378 isAligned]), @"blend": @((double)[c378 blend]),
      @"quality": q378 ? (NSString*)[q378 summary] : @"", @"rms": @(q378 ? (double)[q378 rmsMM] : -1), @"verdict": @(q378 ? (long)[q378 verdict] : -1), @"generation": @((long)[c378 generation])}];
  }
  r378R[@"companions"] = comp378;
  APPLY
}
'''.replace('APPLY', 'if (plan378) r378R[@"added"] = @((long)[r378A horosApplyGuidedCopyPlan:plan378 fromViewer:r378B]);' if args.command == 'apply' else '')
    body += dump
elif args.command == 'dump':
    body = dump
elif args.command == 'undo':
    body = 'if (r378A) (void)[r378A undo:nil];\n' + dump
elif args.command in ('rename', 'restore'):
    old, new = ('L4', 'X') if args.command == 'rename' else ('X', 'L4')
    body = r'''
if (r378B) for (NSArray *sl378 in (NSArray*)[r378B roiList:0]) for (id roi378 in sl378) if ([(NSString*)[roi378 name] isEqualToString:OLD]) (void)[roi378 setName:NEW];
'''.replace('OLD', s(old)).replace('NEW', s(new)) + dump
elif args.command == 'blend':
    body = r'''
if (r378A) {
  NSSlider *sl378 = (NSSlider*)[r378A blendingSlider];
  double lo378 = (double)[sl378 minValue], hi378 = (double)[sl378 maxValue];
  (void)[sl378 setDoubleValue:lo378 + 0.25 * (hi378 - lo378)];
  (void)[r378A blendingSlider:sl378];
  NSMutableArray *panes378 = [NSMutableArray array];
  for (id v378 in (NSArray*)[(id)[r378A seriesView] imageViews]) (void)[panes378 addObject:@((double)(float)[v378 blendingFactor])];
  r378R[@"sliderRange"] = @[@(lo378), @(hi378)]; r378R[@"sliderValue"] = @((double)[sl378 doubleValue]); r378R[@"panes"] = panes378;
  id session378 = (id)[r378A horosRegistrationSession];
  NSMutableArray *comp378 = [NSMutableArray array];
  for (id c378 in (NSArray*)[session378 companions]) (void)[comp378 addObject:@{@"series": (NSString*)[c378 seriesInstanceUID], @"blend": @((double)[c378 blend]), @"aligned": @((BOOL)[c378 isAligned]), @"generation": @((long)[c378 generation])}];
  r378R[@"companions"] = comp378;
}
'''
elif args.command == 'comparison':
    body = r'''
if (r378A && r378Other) {
  r378R[@"pendingBefore"] = (NSString*)[r378A horosPatientComparisonPendingWithViewer:r378Other] ?: @"";
  r378R[@"pendingSamePatient"] = r378B ? ((NSString*)[r378A horosPatientComparisonPendingWithViewer:r378B] ?: @"") : @"n/a";
  (void)[r378A horosConfirmPatientComparisonWithViewer:r378Other];
  r378R[@"pendingAfter"] = (NSString*)[r378A horosPatientComparisonPendingWithViewer:r378Other] ?: @"";
  r378R[@"stored"] = (NSArray*)[[NSUserDefaults standardUserDefaults] arrayForKey:@"HorosPatientComparisonSelections"] ?: @[];
}
'''

expression = preamble + body + '(void)[[NSJSONSerialization dataWithJSONObject:r378R options:3 error:nil] writeToFile:' + s(staged) + ' atomically:YES];\n'
commands = out_dir / (label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\nexpression -l objc++ -- @import Darwin\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (label + '.log')))
staged.replace(report)
data = json.loads(report.read_text())
print(json.dumps({k: v for k, v in data.items() if k not in ('rois', 'placements', 'stored')}, sort_keys=True)[:1200])
