#!/usr/bin/env python3
"""Capture the browser's study list and measure the name cells (#380, A300).

A300 asks for a comparable before/after on a long patient/study list while
scrolling, selecting and resizing, in light and dark, on Retina. This drives the
running development build through lldb: it sets the appearance, turns
`displaySamePatientWithColorBackground` on, makes the outline view first
responder (the host only paints the background then), scrolls/selects/resizes as
asked, and renders the outline view itself into a bitmap at the screen's scale.

`--before` only labels the capture: the pre-fix state is produced by reverting
the two source hunks of the fix and rebuilding, because AppKit answers the
semantic colour selectors from a cache and exchanging their implementations at
runtime does not change the colour that is drawn (measured: the exchange moves
the IMPs and the colour stays).

Every capture records the resolved `unemphasizedSelectedContentBackgroundColor`
and the colour the cell was actually given, so a capture cannot be attributed to
the wrong build.

    python3 tools/capture-native-browser-rows.py --pid N --appearance dark --action scroll --label dark-scroll
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--appearance', choices=['light', 'dark'], default='light')
parser.add_argument('--action', choices=['none', 'scroll', 'select', 'resize'], default='none')
parser.add_argument('--before', action='store_true', help='label this capture as taken on the pre-fix build')
parser.add_argument('--scale', type=int, default=0, help='render at this pixel scale instead of the screen\'s (2 renders the same drawing code at Retina density on a 1x display)')
parser.add_argument('--label', required=True)
parser.add_argument('--output', type=Path, default=Path('local-validation/issue-380-native'))
args = parser.parse_args()
if args.pid <= 0 or not re.fullmatch('[a-z0-9-]+', args.label):
    parser.error('positive PID and a lowercase label')
args.output.mkdir(parents=True, exist_ok=True)
out_dir = args.output.resolve()
report = out_dir / (args.label + '.json')
staged = report.with_name(report.name + '.' + uuid.uuid4().hex + '.partial')


def s(value):
    return '@' + json.dumps(str(value))


expression = r'''
id b380 = (id)[(id)objc_getClass("BrowserController") currentBrowser];
NSMutableDictionary *r380 = [NSMutableDictionary dictionary];
NSOutlineView *o380 = (NSOutlineView*)[b380 databaseOutline];
NSWindow *w380 = (NSWindow*)[b380 window];
(void)[[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"displaySamePatientWithColorBackground"];
(void)[w380 setAppearance:[NSAppearance appearanceNamed:APPEARANCE]];
(void)[w380 makeKeyAndOrderFront:nil];
(void)[w380 makeFirstResponder:o380];
SEED
ACTION
(void)[o380 setNeedsDisplay:YES];
(void)[o380 displayIfNeeded];
NSRect f380 = [(NSView*)o380 bounds];
NSBitmapImageRep *rep380 = nil;
long scale380 = SCALE;
if (scale380 > 0) {
  unsigned char *planes380 = NULL;
  rep380 = (NSBitmapImageRep*)[(NSBitmapImageRep*)[NSBitmapImageRep alloc] initWithBitmapDataPlanes:&planes380
    pixelsWide:(long)(f380.size.width * scale380) pixelsHigh:(long)(f380.size.height * scale380)
    bitsPerSample:(long)8 samplesPerPixel:(long)4 hasAlpha:(BOOL)YES isPlanar:(BOOL)NO
    colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:(long)0 bitsPerPixel:(long)0];
  (void)[rep380 setSize:f380.size];
  NSGraphicsContext *g380 = [NSGraphicsContext graphicsContextWithBitmapImageRep:rep380];
  (void)[NSGraphicsContext saveGraphicsState];
  (void)[NSGraphicsContext setCurrentContext:g380];
  (void)[(NSView*)o380 displayRectIgnoringOpacity:f380 inContext:g380];
  (void)[NSGraphicsContext restoreGraphicsState];
} else {
  rep380 = (NSBitmapImageRep*)[(NSView*)o380 bitmapImageRepForCachingDisplayInRect:f380];
  (void)[(NSView*)o380 cacheDisplayInRect:f380 toBitmapImageRep:rep380];
}
NSData *png380 = (NSData*)[rep380 representationUsingType:(NSBitmapImageFileType)4 properties:@{}];
(void)[png380 writeToFile:PNG atomically:YES];
NSData *raw380 = [NSData dataWithBytes:(const void*)[rep380 bitmapData] length:(NSUInteger)([rep380 bytesPerRow] * [rep380 pixelsHigh])];
(void)[raw380 writeToFile:RAW atomically:YES];
r380[@"width"] = @((long)[rep380 pixelsWide]); r380[@"height"] = @((long)[rep380 pixelsHigh]);
r380[@"bytesPerRow"] = @((long)[rep380 bytesPerRow]); r380[@"samplesPerPixel"] = @((long)[rep380 samplesPerPixel]);
r380[@"backingScaleFactor"] = @((double)[w380 backingScaleFactor]);
r380[@"appearance"] = (NSString*)[(id)[w380 effectiveAppearance] name];
r380[@"rows"] = @((long)[o380 numberOfRows]);
r380[@"selectedRow"] = @((long)[o380 selectedRow]);
r380[@"selectedPatientUID"] = (NSString*)[(NSObject*)[o380 itemAtRow:[o380 selectedRow]] valueForKey:@"patientUID"] ?: @"";
NSRect v380 = (NSRect)[(NSView*)o380 visibleRect];
r380[@"visibleRect"] = @[@((double)v380.origin.x), @((double)v380.origin.y), @((double)v380.size.width), @((double)v380.size.height)];
r380[@"firstResponderIsOutline"] = @((BOOL)((id)[w380 firstResponder] == (id)o380));
r380[@"outlineSize"] = @[@((double)f380.size.width), @((double)f380.size.height)];
NSMutableArray *cols380 = [NSMutableArray array];
for (NSTableColumn *c380 in (NSArray*)[o380 tableColumns]) (void)[cols380 addObject:@{@"id": (NSString*)[c380 identifier], @"width": @((double)[c380 width])}];
r380[@"columns"] = cols380;
NSMutableArray *names380 = [NSMutableArray array];
for (long i380 = 0; i380 < (long)[o380 numberOfRows] && i380 < 400; i380++) {
  id it380 = (id)[o380 itemAtRow:i380];
  NSRect rr380 = (NSRect)[o380 rectOfRow:i380];
  (void)[names380 addObject:@{@"row": @(i380), @"type": (NSString*)[(NSObject*)it380 valueForKey:@"type"] ?: @"",
    @"name": (NSString*)[(NSObject*)it380 valueForKey:@"name"] ?: @"",
    @"patientUID": (NSString*)[(NSObject*)it380 valueForKey:@"patientUID"] ?: @"",
    @"rect": @[@((double)rr380.origin.x), @((double)rr380.origin.y), @((double)rr380.size.width), @((double)rr380.size.height)]}];
}
r380[@"visibleRows"] = names380;
r380[@"before"] = @(BEFOREFLAG);
{ NSColor *c380 = [(NSColor*)[NSColor unemphasizedSelectedContentBackgroundColor] colorUsingColorSpace:[NSColorSpace sRGBColorSpace]];
  r380[@"unemphasizedColour"] = @[@((double)[c380 redComponent]), @((double)[c380 greenComponent]), @((double)[c380 blueComponent]), @((double)[c380 alphaComponent])]; }
{ NSColor *d380 = [(NSColor*)[NSColor disabledControlTextColor] colorUsingColorSpace:[NSColorSpace sRGBColorSpace]];
  r380[@"disabledTextColour"] = @[@((double)[d380 redComponent]), @((double)[d380 greenComponent]), @((double)[d380 blueComponent]), @((double)[d380 alphaComponent])]; }
r380[@"renderScale"] = @(scale380 > 0 ? scale380 : (long)[w380 backingScaleFactor]);
'''

seed = ('{ long sel380 = -1; for (long i380 = 1; i380 + 1 < (long)[o380 numberOfRows]; i380++) { '
        'id a380 = (id)[o380 itemAtRow:i380 - 1], b380 = (id)[o380 itemAtRow:i380]; '
        'NSString *ua380 = (NSString*)[(NSObject*)a380 valueForKey:@"patientUID"], *ub380 = (NSString*)[(NSObject*)b380 valueForKey:@"patientUID"]; '
        'if ([ua380 length] > 1 && [ua380 isEqualToString:ub380]) { sel380 = i380; break; } } '
        'if (sel380 >= 0) { (void)[o380 selectRowIndexes:[NSIndexSet indexSetWithIndex:sel380] byExtendingSelection:NO]; (void)[o380 scrollRowToVisible:sel380]; } }')

actions = {
    'none': '',
    'scroll': '(void)[o380 scrollRowToVisible:(long)[o380 numberOfRows] - 1]; (void)[o380 scrollRowToVisible:MIN((long)[o380 numberOfRows] - 1, 12)];',
    'select': '(void)[o380 selectRowIndexes:[NSIndexSet indexSetWithIndex:(long)[o380 selectedRow] + 1] byExtendingSelection:NO]; (void)[o380 scrollRowToVisible:(long)[o380 selectedRow]];',
    'resize': ('{ NSTableColumn *n380 = (NSTableColumn*)[o380 tableColumnWithIdentifier:@"name"]; (void)[n380 setWidth:(double)[n380 width] * 0.6]; '
               '(void)[o380 tile]; (void)[n380 setWidth:(double)[n380 width] / 0.6]; (void)[o380 tile]; '
               '(void)[o380 scrollRowToVisible:MIN((long)[o380 numberOfRows] - 1, 12)]; }'),
}
expression = (expression
              .replace('APPEARANCE', '@"NSAppearanceNameDarkAqua"' if args.appearance == 'dark' else '@"NSAppearanceNameAqua"')
              .replace('SEED', seed)
              .replace('ACTION', actions[args.action])
              .replace('BEFOREFLAG', 'YES' if args.before else 'NO')
              .replace('SCALE', str(args.scale))
              .replace('PNG', s(out_dir / (args.label + '.png')))
              .replace('RAW', s(out_dir / (args.label + '.raw'))))
expression += '(void)[[NSJSONSerialization dataWithJSONObject:r380 options:3 error:nil] writeToFile:' + s(staged) + ' atomically:YES];\n'
commands = out_dir / (args.label + '.lldb')
commands.write_text('expression -l objc++ -- @import AppKit\nexpression -l objc++ -- @import ObjectiveC\n'
                    'expression -l objc++ -- { ' + ' '.join(expression.splitlines()) + ' }\nprocess detach\n')
result = subprocess.run(['xcrun', 'lldb', '--batch', '-p', str(args.pid), '-s', str(commands)], capture_output=True, text=True)
(out_dir / (args.label + '.log')).write_text(result.stdout + result.stderr)
if result.returncode or not staged.exists():
    raise SystemExit('lldb step failed; inspect ' + str(out_dir / (args.label + '.log')))
staged.replace(report)
data = json.loads(report.read_text())
print(json.dumps({k: v for k, v in data.items() if k != 'visibleRows'}, sort_keys=True))
