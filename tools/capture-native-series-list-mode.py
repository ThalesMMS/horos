#!/usr/bin/env python3
"""Read synthetic A273 viewer/panel state through LLDB; never drive the UI.

See docs/series-list-mode-validation.md. The target is briefly paused; all
collected identifiers and logs stay in the selected local output directory.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('label', help='Snapshot label used by the native verifier')
parser.add_argument('--pid', type=int, required=True, help='Current isolated development process')
parser.add_argument('--output', type=Path, default=Path('local-validation/series-list-mode'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('Use a positive PID and a lowercase snapshot label')
args.output.mkdir(parents=True, exist_ok=True)
output = (args.output / (args.label + '.json')).resolve()
staged = output.with_name(output.name + '.' + uuid.uuid4().hex + '.partial')
expression = r'''
NSMutableDictionary *a273State=[NSMutableDictionary dictionary];
a273State[@"floating"]=@([[NSUserDefaults standardUserDefaults] boolForKey:@"UseFloatingThumbnailsList"]);
a273State[@"listVisible"]=@([[NSUserDefaults standardUserDefaults] boolForKey:@"SeriesListVisible"]);
a273State[@"keyWindow"]=[(NSApplication*)NSApp keyWindow].title ?: @"";
a273State[@"screenCount"]=@([NSScreen screens].count);
NSMutableArray *a273Viewers=[NSMutableArray array];
for(id a273Vc in (id)[(id)objc_getClass("ViewerController") get2DViewers]) { NSWindow *a273Window=(id)[a273Vc window];
NSScrollView *a273Scroll=(id)[a273Vc previewMatrixScrollView];
NSMatrix *a273Matrix=(id)[a273Scroll documentView];
id a273Image=(id)[a273Vc imageView];
id a273Pix=(id)[a273Image curDCM];
NSSplitView *a273Split=(id)[a273Vc valueForKey:@"splitView"];
NSMutableDictionary *a273S=[NSMutableDictionary dictionary];
a273S[@"controller"]=[NSString stringWithFormat:@"%p",a273Vc];
a273S[@"windowNumber"]=@(a273Window.windowNumber);
a273S[@"windowVisible"]=@(a273Window.isVisible);
a273S[@"windowFrame"]=NSStringFromRect(a273Window.frame);
a273S[@"title"]=a273Window.title;
a273S[@"matrix"]=[NSString stringWithFormat:@"%p",a273Matrix];
a273S[@"scroll"]=[NSString stringWithFormat:@"%p",a273Scroll];
a273S[@"currentImage"]=@((long)[a273Image curImage]);
a273S[@"pixList"]=[NSString stringWithFormat:@"%p",(id)[a273Vc pixList]];
a273S[@"pixCount"]=@([(NSArray *)(id)[a273Vc pixList] count]);
a273S[@"roiList"]=[NSString stringWithFormat:@"%p",(id)[a273Vc roiList]];
a273S[@"roiCount"]=@([(NSArray *)(id)[a273Image valueForKey:@"curRoiList"] count]);
a273S[@"zoom"]=@((float)[a273Image scaleValue]);
a273S[@"rows"]=@(a273Matrix.numberOfRows);
a273S[@"selectedRow"]=@(a273Matrix.selectedRow);
a273S[@"matrixWindowClass"]=NSStringFromClass(a273Matrix.window.class) ?: @"nil";
a273S[@"matrixWindowVisible"]=@(a273Matrix.window.isVisible);
a273S[@"matrixParentClass"]=NSStringFromClass(a273Scroll.superview.class) ?: @"nil";
a273S[@"scrollFrame"]=NSStringFromRect(a273Scroll.frame);
a273S[@"splitSubviews"]=@(a273Split.subviews.count);
a273S[@"dockHidden"]=@(a273Split.subviews.firstObject.isHidden);
a273S[@"dockFrame"]=NSStringFromRect(a273Split.subviews.firstObject.frame);
NSMutableArray *a273Cells=[NSMutableArray array];
for(NSCell *a273Cell in a273Matrix.cells) [a273Cells addObject:@{@"title":a273Cell.title ?: @"",@"state":@(a273Cell.state), @"background":[(NSButtonCell*)a273Cell backgroundColor].description ?: @""}];
a273S[@"cells"]=a273Cells;
[a273Viewers addObject:a273S];
} a273State[@"viewers"]=a273Viewers;
NSMutableArray *a273Panels=[NSMutableArray array];
for(NSWindow *a273W in [(NSApplication*)NSApp windows]) if([NSStringFromClass(a273W.class) isEqualToString:@"ThumbnailsListNSWindow"]){id a273Owner=(id)[(id)a273W.windowController viewer];
[a273Panels addObject:@{@"visible":@(a273W.isVisible), @"frame":NSStringFromRect(a273W.frame), @"owner":[NSString stringWithFormat:@"%p",a273Owner], @"ownerTitle":[(NSWindow *)(id)[a273Owner window] title] ?: @"", @"panelController":a273W.windowController.description ?: @"", @"panelScreen":[(NSObject*)a273W.windowController valueForKey:@"screen"], @"panelScroll":[NSString stringWithFormat:@"%p",(id)[(id)a273W.windowController thumbnailsView]], @"windowNumber":@(a273W.windowNumber)}];} a273State[@"panels"]=a273Panels;
[[NSJSONSerialization dataWithJSONObject:a273State options:3 error:nil]writeToFile:OUTPUT atomically:YES];
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
if not state['viewers'] or any(v['title'].strip() not in allowed for v in state['viewers']):
    raise SystemExit('Wait for the two synthetic series to finish opening before capturing')
staged.replace(output)
print(args.label + ': captured ' + str(len(state['viewers'])) + ' synthetic viewer(s)')
