#!/usr/bin/env python3
"""Move the viewer's series list to each edge and measure what happens (#380 D).

Drives the menu action the user has (`setSeriesListPlacement:`, tags 0..3 =
left, right, top, bottom) on the front 2D viewer of the running development
build and records, for each edge: the split view's orientation, which pane the
dock is, the dock and list frames, the matrix's rows, columns and cell size,
the document size against the visible size (a strip that cannot fit its
thumbnails must scroll, not shrink them), the number of cells and their
represented series, and the stored preference.

    python3 tools/exercise-native-series-list.py --pid N
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--label', default='series-list-placement')
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-380-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('positive PID and a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')

expression = r'''
NSMutableDictionary *s380 = [NSMutableDictionary dictionary];
id vc380 = nil;
for (id c in (NSArray*)[(id)objc_getClass("ViewerController") get2DViewers]) {
  if ((long)[(NSArray*)[c pixList] count] > 1 && vc380 == nil) vc380 = c;
}
s380[@"viewer"] = @(vc380 != nil);
NSMutableArray *states380 = [NSMutableArray array];
if (vc380) {
  (void)[[NSUserDefaults standardUserDefaults] setBool:NO forKey:@"UseFloatingThumbnailsList"];
  (void)[[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"SeriesListVisible"];
  (void)[vc380 updateSeriesListMode];
  for (long p380 = 0; p380 < 4; p380++) {
    id item380 = [[NSMenuItem alloc] initWithTitle:@"placement" action:nil keyEquivalent:@""];
    (void)[item380 setTag:p380];
    (void)[vc380 setSeriesListPlacement:item380];
    (void)[vc380 updateSeriesListMode];
    NSScrollView *sv380 = (NSScrollView*)[vc380 previewMatrixScrollView];
    id matrix380 = (id)[sv380 documentView];
    NSSplitView *split380 = (NSSplitView*)[(NSObject*)vc380 valueForKey:@"splitView"];
    NSView *dock380 = (NSView*)[sv380 superview];
    NSRect dr380 = (NSRect)[dock380 frame], mr380 = (NSRect)[(NSView*)matrix380 frame], vr380 = (NSRect)[sv380 documentVisibleRect];
    NSSize cs380 = (NSSize)[matrix380 cellSize];
    NSMutableArray *titles380 = [NSMutableArray array];
    for (id cell380 in (NSArray*)[matrix380 cells]) (void)[titles380 addObject:(NSString*)[cell380 title] ?: @""];
    (void)[states380 addObject:@{
      @"placement": (NSString*)[(Class)objc_getClass("HorosSeriesListLayout") nameOfPlacement:(long)p380],
      @"stored": (NSString*)[[NSUserDefaults standardUserDefaults] stringForKey:@"HorosSeriesListPlacement"] ?: @"",
      @"isVertical": @((BOOL)[split380 isVertical]),
      @"dockIsFirstPane": @((BOOL)((id)[(NSArray*)[split380 subviews] objectAtIndex:0] == (id)dock380)),
      @"panes": @((long)[(NSArray*)[split380 subviews] count]),
      @"dockFrame": @[@((double)dr380.origin.x), @((double)dr380.origin.y), @((double)dr380.size.width), @((double)dr380.size.height)],
      @"matrixFrame": @[@((double)mr380.size.width), @((double)mr380.size.height)],
      @"visibleSize": @[@((double)vr380.size.width), @((double)vr380.size.height)],
      @"rows": @((long)[matrix380 numberOfRows]), @"columns": @((long)[matrix380 numberOfColumns]),
      @"cellSize": @[@((double)cs380.width), @((double)cs380.height)],
      @"cells": @((long)[(NSArray*)[matrix380 cells] count]),
      @"titles": titles380,
      @"hasHorizontalScroller": @((BOOL)[sv380 hasHorizontalScroller]),
      @"hasVerticalScroller": @((BOOL)[sv380 hasVerticalScroller])}];
  }
}
s380[@"states"] = states380;
'''
expression += '(void)[[NSJSONSerialization dataWithJSONObject:s380 options:3 error:nil] writeToFile:@' + json.dumps(str(staged)) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
data = json.loads(report.read_text())
for state in data.get('states', []):
    print('%-6s stored %-6s vertical %d dockFirst %d dock %s matrix %s visible %s %dx%d cells %d cell %s scrollers h%d v%d'
          % (state['placement'], state['stored'], state['isVertical'], state['dockIsFirstPane'],
             state['dockFrame'], state['matrixFrame'], state['visibleSize'], state['rows'], state['columns'],
             state['cells'], state['cellSize'], state['hasHorizontalScroller'], state['hasVerticalScroller']))
