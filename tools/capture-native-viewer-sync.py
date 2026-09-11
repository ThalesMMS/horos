#!/usr/bin/env python3
"""Read A294 synthetic viewer state, without driving the UI through LLDB.

Use only with the isolated MR pair from generate-cross-reference-fixture.py.
See docs/viewer-synchronisation-a294.md. Captures and debugger logs stay local.
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
parser.add_argument('--output', type=Path, default=Path('local-validation/viewer-sync'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('Use a positive PID and a lowercase snapshot label')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / (args.label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')
expression = r'''
NSMutableDictionary *a294State=[NSMutableDictionary dictionary];
a294State[@"syncMode"]=@((short)[(id)objc_getClass("DCMView") syncro]);
a294State[@"automaticTabbing"]=@(NSWindow.allowsAutomaticWindowTabbing);
a294State[@"systemTabbing"]=[[NSUserDefaults standardUserDefaults] stringForKey:@"AppleWindowTabbingMode"] ?: @"";
a294State[@"closeBeforeOpen"]=@([[NSUserDefaults standardUserDefaults] boolForKey:@"CloseAllWindowsBeforeXMLRPCOpen"]);
a294State[@"keyWindow"]=[(NSApplication*)NSApp keyWindow].title ?: @"";
a294State[@"applicationActive"]=@([(NSApplication*)NSApp isActive]);
a294State[@"screenCount"]=@([NSScreen screens].count);
NSMutableArray *a294Viewers=[NSMutableArray array];
for(id a294Vc in (id)[(id)objc_getClass("ViewerController") get2DViewers]) {
NSWindow *a294Window=(id)[a294Vc window]; id a294Image=(id)[a294Vc imageView]; id a294Pix=(id)[a294Image curDCM];
NSMutableDictionary *a294V=[NSMutableDictionary dictionary];
a294V[@"controller"]=[NSString stringWithFormat:@"%p",a294Vc];
a294V[@"windowNumber"]=@(a294Window.windowNumber);
a294V[@"visible"]=@(a294Window.isVisible);
a294V[@"miniaturized"]=@(a294Window.isMiniaturized);
a294V[@"key"]=@(a294Window.isKeyWindow);
a294V[@"main"]=@(a294Window.isMainWindow);
a294V[@"title"]=a294Window.title;
NSRect a294F=a294Window.frame;
a294V[@"frame"]=@[@(a294F.origin.x),@(a294F.origin.y),@(a294F.size.width),@(a294F.size.height)];
a294V[@"tabbedCount"]=@(a294Window.tabbedWindows.count);
a294V[@"tabGroupCount"]=@(a294Window.tabGroup.windows.count);
a294V[@"isKeyView"]=@((BOOL)[a294Image isKeyView]);
a294V[@"currentTool"]=@((long)[a294Image currentTool]);
a294V[@"metalEnabled"]=@((BOOL)[a294Vc horosPlanarMetalEnabled]);
a294V[@"fallback"]=(id)[a294Image horosPlanarFallbackReason] ?: @"";
a294V[@"lastMetalCommandMilliseconds"]=@((double)[a294Image horosPlanarLastCommandMilliseconds]);
a294V[@"flippedData"]=@((BOOL)[a294Image flippedData]);
a294V[@"currentImage"]=@((long)[a294Image curImage]);
a294V[@"location"]=@((double)[a294Pix sliceLocation]);
a294V[@"pixCount"]=@([(NSArray *)(id)[a294Vc pixList] count]);
a294V[@"pixList"]=[NSString stringWithFormat:@"%p",(id)[a294Vc pixList]];
a294V[@"roiList"]=[NSString stringWithFormat:@"%p",(id)[a294Vc roiList]];
[a294Viewers addObject:a294V];
} a294State[@"viewers"]=a294Viewers;
[[NSJSONSerialization dataWithJSONObject:a294State options:3 error:nil]writeToFile:OUTPUT atomically:YES];
'''.replace('OUTPUT', '@' + json.dumps(str(staged)))
commands = args.output / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\n'
                    'process detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)],
                        capture_output=True, text=True)
(args.output / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('Capture failed; inspect the local LLDB log')
state = json.loads(staged.read_text())
allowed = {'Crossref Axial Pair A (5)', 'Crossref Axial Pair B (6)'}
if {v['title'].strip() for v in state['viewers']} != allowed or len(state['viewers']) != 2:
    raise SystemExit('Wait for exactly the two synthetic MR viewers to finish opening')
staged.replace(output)
print(args.label + ': mode ' + str(state['syncMode']) + ', ' + ', '.join(
    v['title'].strip() + '=' + str(v['currentImage']) for v in state['viewers']))
