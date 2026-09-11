#!/usr/bin/env python3
"""Drive the SEG Surfaces panel of the running viewer and capture what its windows draw (#377 A/B).

Each subcommand attaches lldb once to the dev build (see the native harness
notes), acts on the viewer of the synthetic surface CT (patient SYNTHETIC-377,
sixteen slices) and writes `<label>.json` plus raw RGB captures under
`local-validation/issue-377-native/`. Captures go through the host's own
`getRawPixels` screen-capture path, so they hold exactly what each OpenGL
view drew, overlays included. Nothing here is a claim about pixels; the
comparison is `tools/compare-native-seg-surfaces.py`.

    python3 tools/capture-native-seg-surfaces.py --pid N import <file> --label seg
    python3 tools/capture-native-seg-surfaces.py --pid N open3d   # 3D MPR; open the VR through the 3D Viewer menu with the viewer in front
    python3 tools/capture-native-seg-surfaces.py --pid N capture visible
    python3 tools/capture-native-seg-surfaces.py --pid N visible 0
    python3 tools/capture-native-seg-surfaces.py --pid N undo 4
    python3 tools/capture-native-seg-surfaces.py --pid N close vr|mpr|panel|viewer
    python3 tools/capture-native-seg-surfaces.py --pid N state --label after-close
    python3 tools/capture-native-seg-surfaces.py --pid N slice 5
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-377-native'))
parser.add_argument('--label', default=None)
parser.add_argument('--patient', default='SYNTHETIC-377')
parser.add_argument('--slices', type=int, default=16)
sub = parser.add_subparsers(dest='command', required=True)
p = sub.add_parser('import'); p.add_argument('file', type=Path)
sub.add_parser('open3d')
p = sub.add_parser('capture'); p.add_argument('state')
p = sub.add_parser('visible'); p.add_argument('flag', type=int, choices=[0, 1])
p = sub.add_parser('undo'); p.add_argument('count', type=int)
p = sub.add_parser('close'); p.add_argument('what', choices=['vr', 'mpr', 'panel', 'viewer'])
sub.add_parser('state')
p = sub.add_parser('slice'); p.add_argument('index', type=int)
args = parser.parse_args()
if args.pid <= 0:
    parser.error('positive PID required')
label = args.label or {'capture': lambda: args.state, 'visible': lambda: 'set-visible-%d' % args.flag,
                       'close': lambda: 'close-' + args.what}.get(args.command, lambda: args.command)()
if not re.fullmatch('[a-z0-9-]+', label):
    parser.error('label must be lowercase letters, digits and dashes')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')

def s(value):
    return '@' + json.dumps(str(value))

preamble = r'''
id s377VC = nil;
for (id c in (NSArray*)[(id)objc_getClass("ViewerController") get2DViewers]) {
  NSString *pid377 = (NSString*)[(NSObject*)[c currentStudy] valueForKey:@"patientID"];
  if ([pid377 isEqualToString:PATIENT] && (long)[(NSArray*)[c pixList] count] == SLICES) s377VC = c;
}
id s377Other = nil;
for (id c in (NSArray*)[(id)objc_getClass("ViewerController") get2DViewers]) { if (c != s377VC) s377Other = c; }
id s377Ctrl = nil; id s377MPR = nil; id s377VR = nil; long s377Panels = 0;
for (NSWindow *w in (id)[(NSApplication*)NSApp windows]) {
  id wc = (id)[w windowController];
  if (!wc) continue;
  if ((BOOL)[wc isKindOfClass:(Class)objc_getClass("HorosSEGSurfaceController")] && (BOOL)[w isVisible]) { s377Ctrl = wc; s377Panels++; }
  if ((BOOL)[wc isKindOfClass:(Class)objc_getClass("MPRController")] && (id)[(NSObject*)wc valueForKey:@"viewer2D"] == s377VC && (BOOL)[w isVisible]) s377MPR = wc;
  if ((BOOL)[wc isKindOfClass:(Class)objc_getClass("VRController")] && (id)[(NSObject*)wc valueForKey:@"viewer2D"] == s377VC && (BOOL)[w isVisible]) s377VR = wc;
}
id s377Session = s377Ctrl ? (id)[(NSObject*)s377Ctrl valueForKey:@"session"] : nil;
NSMutableDictionary *s377R = [NSMutableDictionary dictionary];
s377R[@"viewer"] = @(s377VC != nil); s377R[@"otherViewer"] = @(s377Other != nil);
s377R[@"panels"] = @(s377Panels); s377R[@"mpr"] = @(s377MPR != nil); s377R[@"vr"] = @(s377VR != nil);
s377R[@"sessionCurrent"] = @(s377Session ? (BOOL)[s377Session isCurrent] : NO);
s377R[@"viewers"] = @((long)[(NSArray*)[(id)objc_getClass("ViewerController") get2DViewers] count]);
'''.replace('PATIENT', s(args.patient)).replace('SLICES', str(args.slices))

snapshots = r'''
NSMutableArray *s377S = [NSMutableArray array];
if (s377Session) for (id sf in (NSArray*)[s377Session snapshots]) {
  (void)[s377S addObject:@{@"number": @((long)(unsigned short)[sf number]), @"label": (NSString*)[sf label], @"visible": @((BOOL)[sf visible]),
    @"opacity": @((double)[sf opacity]), @"red": @((double)[sf red]), @"green": @((double)[sf green]), @"blue": @((double)[sf blue]),
    @"vertices": @((long)[(NSData*)[(id)[sf mesh] vertices] length] / 24), @"triangles": @((long)[(NSData*)[(id)[sf mesh] triangles] length] / 24), @"meshCm3": @((double)[(id)[sf mesh] meshVolumeCm3]), @"maskCm3": @((double)[(id)[sf mesh] maskVolumeCm3]), @"closed": @((BOOL)[(id)[sf mesh] closed])}];
}
s377R[@"surfaces"] = s377S;
'''

body = ''
if args.command == 'import':
    body = r'''
if (s377VC) {
  (void)[s377VC showSEGSurfaces:nil];
  for (NSWindow *w in (id)[(NSApplication*)NSApp windows]) { id wc = (id)[w windowController]; if (wc && (BOOL)[wc isKindOfClass:(Class)objc_getClass("HorosSEGSurfaceController")]) s377Ctrl = wc; }
  s377Session = s377Ctrl ? (id)[(NSObject*)s377Ctrl valueForKey:@"session"] : nil;
  NSData *s377D = [NSData dataWithContentsOfFile:FILE];
  mach_timebase_info_data_t s377TB; (void)mach_timebase_info(&s377TB);
  uint64_t t0 = mach_absolute_time();
  NSString *s377Diag = (NSString*)[s377Session loadData:s377D];
  uint64_t t1 = mach_absolute_time();
  s377R[@"bytes"] = @((long)[s377D length]);
  s377R[@"diagnosis"] = s377Diag ?: @"";
  s377R[@"importMilliseconds"] = @((double)(t1 - t0) * s377TB.numer / s377TB.denom / 1e6);
  s377R[@"sessionCurrent"] = @((BOOL)[s377Session isCurrent]);
}
'''.replace('FILE', s(args.file.resolve()))
elif args.command == 'open3d':
    body = r'''
if (s377VC) { if (!s377MPR) (void)[s377VC openMPRViewer]; s377R[@"opened"] = @YES; }
'''
elif args.command == 'capture':
    capture = r'''
{ long cw = 0, ch = 0, cs = 0, cb = 0;
  unsigned char *cp = (unsigned char*)[VIEW getRawPixels:&cw :&ch :&cs :&cb :(BOOL)1 :(BOOL)1];
  if (cp) { (void)[[NSData dataWithBytesNoCopy:cp length:(NSUInteger)(cw*ch*cs*(cb/8)) freeWhenDone:YES] writeToFile:PATH atomically:YES];
    s377R[NAME] = @{@"width": @(cw), @"height": @(ch), @"spp": @(cs), @"bpp": @(cb)}; } }
'''
    parts = [('twoD', '(id)[s377VC imageView]', 'if (s377VC)'),
             ('other', '(id)[s377Other imageView]', 'if (s377Other)'),
             ('mpr1', '(id)[s377MPR mprView1]', 'if (s377MPR)'),
             ('mpr2', '(id)[s377MPR mprView2]', 'if (s377MPR)'),
             ('mpr3', '(id)[s377MPR mprView3]', 'if (s377MPR)'),
             ('vrView', '(id)[s377VR view]', 'if (s377VR)')]
    for name, view, guard in parts:
        body += guard + capture.replace('VIEW', view).replace('PATH', s(out_dir / (label + '.' + name + '.rgb'))).replace('NAME', '@' + json.dumps(name))
elif args.command == 'visible':
    body = r'''
if (s377Session) for (id sf in [(NSArray*)[s377Session snapshots] copy]) (void)[s377Session setVisible:(unsigned short)[sf number] visible:(BOOL)FLAG];
'''.replace('FLAG', str(args.flag))
elif args.command == 'undo':
    body = r'''
for (int i = 0; i < COUNT; ++i) (void)[s377Session undo];
'''.replace('COUNT', str(args.count))
elif args.command == 'slice':
    body = r'''
if (s377VC) { (void)[(id)[s377VC imageView] setIndex:INDEX]; (void)[s377VC adjustSlider]; (void)[(NSView*)[s377VC imageView] display]; s377R[@"sliceIndex"] = @((long)[(id)[s377VC imageView] curImage]); }
'''.replace('INDEX', str(args.index))
elif args.command == 'close':
    target = {'vr': 's377VR', 'mpr': 's377MPR', 'panel': 's377Ctrl', 'viewer': 's377VC'}[args.what]
    body = r'''
if (TARGET) { (void)[(NSWindow*)[TARGET window] performClose:nil]; s377R[@"closed"] = @YES; }
'''.replace('TARGET', target)

expression = preamble + body + snapshots + '(void)[[NSJSONSerialization dataWithJSONObject:s377R options:3 error:nil] writeToFile:' + s(staged) + ' atomically:YES];\n'
commands = out_dir / (label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\nexpression -l objc++ -- @import Darwin\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (label + '.log')))
staged.replace(report)
print(json.dumps(json.loads(report.read_text()), sort_keys=True)[:1500])
