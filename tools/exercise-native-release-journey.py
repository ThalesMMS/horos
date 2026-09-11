#!/usr/bin/env python3
"""One study carried through the whole chain, on the running build (#385).

The release gate asks for the journey, not for each leg on its own: import and
retrieve, planar, MPR, 3D, ROI, persist, reopen and export. Each step is one
lldb attach that *schedules* the host's own action and then reads what came of
it, so nothing modal is called while the process is stopped. Every step also
reports whether a modal window is up, because a panel left unanswered is the
difference between a step that worked and a step that is still waiting.

    python3 tools/exercise-native-release-journey.py --pid N STEP --series NAME

Steps: state, mpr, vr, reopen, close. ROIs are created and read back by the
harness #378 already ships (`tools/exercise-native-registration.py`); this tool
does not build a second route for them.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('step', choices=['state', 'mpr', 'vr', 'reopen', 'close'])
parser.add_argument('--series', default='', help='series name of the viewer to act on')
parser.add_argument('--label', default=None)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-385-native'))
args = parser.parse_args()
args.label = args.label or ('journey-' + args.step)
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('positive PID and a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')

preamble = r'''
NSMutableDictionary *j385 = [NSMutableDictionary dictionary];
j385[@"modal"] = (NSString*)[(NSWindow*)[(NSApplication*)NSApp modalWindow] title] ?: @"(none)";
j385[@"hasModal"] = @((id)[(NSApplication*)NSApp modalWindow] != nil);
NSMutableArray *wins385 = [NSMutableArray array];
for (NSWindow *w385 in (NSArray*)[(NSApplication*)NSApp windows])
  if ((BOOL)[w385 isVisible]) (void)[wins385 addObject: [NSString stringWithFormat: @"%@|%@", NSStringFromClass([w385 class]), [w385 title] ?: @""]];
j385[@"windows"] = wins385;
id v385 = nil;
NSString *wanted385 = SERIES;
for (id c385 in (NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers])
  if (![wanted385 length] || [(NSString*)[(NSObject*)[c385 currentSeries] valueForKey:@"name"] isEqualToString: wanted385]) { v385 = c385; break; }
j385[@"viewer"] = @(v385 != nil);
j385[@"series"] = (NSString*)[(NSObject*)[v385 currentSeries] valueForKey:@"name"] ?: @"";
j385[@"twoDViewers"] = @((long)[(NSArray*)[(Class)objc_getClass("ViewerController") get2DViewers] count]);
'''

steps = {
    'state': r'''
if (v385) {
  j385[@"images"] = @((long)[(NSArray*)[v385 fileList] count]);
  j385[@"patientID"] = (NSString*)[(NSObject*)[v385 currentStudy] valueForKey:@"patientID"] ?: @"";
  j385[@"studyUID"] = (NSString*)[(NSObject*)[v385 currentStudy] valueForKey:@"studyInstanceUID"] ?: @"";
  j385[@"rois"] = @((long)[(NSArray*)[(NSArray*)[v385 roiList] objectAtIndex: 0] count]);
  j385[@"volumic"] = @((BOOL)[v385 isDataVolumicIn4D: YES]);
  id decision385 = (id)[v385 reconstructionOpeningDecision];
  j385[@"decisionAccepted"] = @((BOOL)[decision385 accepted]);
  j385[@"decisionPhase"] = (NSString*)[decision385 phase] ?: @"";
  j385[@"decisionDiagnosis"] = (NSString*)[decision385 diagnosis] ?: @"";
}
NSMutableArray *others385 = [NSMutableArray array];
for (id w385 in (NSArray*)[(NSApplication*)NSApp windows]) {
  id wc385 = (id)[(NSWindow*)w385 windowController];
  if (wc385 && (BOOL)[wc385 isKindOfClass: (Class)objc_getClass("OrthogonalMPRViewer")]) (void)[others385 addObject: @"OrthogonalMPRViewer"];
  if (wc385 && (BOOL)[wc385 isKindOfClass: (Class)objc_getClass("MPRController")]) (void)[others385 addObject: @"MPRController"];
  if (wc385 && (BOOL)[wc385 isKindOfClass: (Class)objc_getClass("VRController")]) (void)[others385 addObject: @"VRController"];
}
j385[@"reconstructionWindows"] = others385;
NSMutableArray *planes385 = [NSMutableArray array];
for (id w385 in (NSArray*)[(NSApplication*)NSApp windows]) {
  id wc385 = (id)[(NSWindow*)w385 windowController];
  if (!(wc385 && (BOOL)[wc385 isKindOfClass: (Class)objc_getClass("OrthogonalMPRViewer")])) continue;
  id ctl385 = (id)[wc385 controller];
  NSArray *names385 = @[@"originalView", @"xReslicedView", @"yReslicedView"];
  for (NSString *name385 in names385) {
    id view385 = (id)[(NSObject*)ctl385 valueForKey: name385];
    id pix385 = (id)[view385 curDCM];
    long w2385 = (long)[pix385 pwidth], h2385 = (long)[pix385 pheight];
    float *buf385 = (float*)[pix385 fImage];
    double sum385 = 0, mn385 = 1e30, mx385 = -1e30; long n385 = 0;
    for (long i385 = 0; buf385 && i385 < w2385 * h2385; i385 += 7) {
      double value385 = (double)buf385[i385];
      sum385 += value385; n385++;
      if (value385 < mn385) mn385 = value385;
      if (value385 > mx385) mx385 = value385;
    }
    (void)[planes385 addObject: @{@"plane": name385, @"width": @(w2385), @"height": @(h2385),
                                  @"mean": @(n385 ? sum385 / (double)n385 : 0),
                                  @"min": @(n385 ? mn385 : 0), @"max": @(n385 ? mx385 : 0),
                                  @"samples": @(n385)}];
  }
}
j385[@"mprPlanes"] = planes385;
''',
    'mpr': r'''
if (v385) (void)[v385 performSelector:@selector(orthogonalMPRViewer:) withObject:nil afterDelay:0.2];
j385[@"scheduled"] = @"orthogonalMPRViewer:";
''',
    'vr': r'''
if (v385) (void)[v385 performSelector:@selector(VRViewer:) withObject:nil afterDelay:0.2];
j385[@"scheduled"] = @"VRViewer:";
''',
    'reopen': r'''
if (v385) {
  j385[@"roisOnReopen"] = @((long)[(NSArray*)[(NSArray*)[v385 roiList] objectAtIndex: 0] count]);
  NSMutableArray *names385 = [NSMutableArray array];
  for (id r385 in (NSArray*)[(NSArray*)[v385 roiList] objectAtIndex: 0])
    (void)[names385 addObject: (NSString*)[r385 name] ?: @""];
  j385[@"roiNames"] = names385;
}
''',
    'close': r'''
NSMutableArray *closed385 = [NSMutableArray array];
for (id w385 in (NSArray*)[(NSArray*)[(NSApplication*)NSApp windows] copy]) {
  id wc385 = (id)[(NSWindow*)w385 windowController];
  if (wc385 && ((BOOL)[wc385 isKindOfClass: (Class)objc_getClass("OrthogonalMPRViewer")]
             || (BOOL)[wc385 isKindOfClass: (Class)objc_getClass("VRController")])) {
    (void)[closed385 addObject: NSStringFromClass([wc385 class])];
    (void)[(NSWindow*)w385 performSelector:@selector(performClose:) withObject:nil afterDelay:0.2];
  }
}
j385[@"closing"] = closed385;
''',
}

expression = preamble.replace('SERIES', '@' + json.dumps(args.series)) + steps[args.step]
expression += '(void)[[NSJSONSerialization dataWithJSONObject:j385 options:3 error:nil] writeToFile:@' + json.dumps(str(staged)) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
print(json.dumps(json.loads(report.read_text()), indent=1)[:1800])
