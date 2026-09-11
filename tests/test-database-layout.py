#!/usr/bin/env python3
"""Exercise production recovery with real AppKit split views and saved preferences."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
s = (root / 'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
a = s.index('- (void)spaceEvenly:')
layout = s[a:s.index('- (NSArray *)toolbarDefaultItemIdentifiers:', a)]
a = s.index('- (IBAction)drawerToggle:')
toggle = s[a:s.index('- (CGFloat)splitView:', a)]
a = s.index('-(void)splitView:(NSSplitView*)sender resizeSubviewsWithOldSize:(NSSize)oldSize\n{')
b = s.index('    if (sender == splitComparative)', a)
resize = s[a:b] + '    [sender adjustSubviews];\n}\n'
code = r'''
#import <AppKit/AppKit.h>
#import "NSSplitViewSave.h"
#define check(c) NSCAssert((c),@"failed: %s",#c)
@interface BrowserProbe:NSObject <NSSplitViewDelegate> {
@public
 NSSplitView *splitDrawer, *splitAlbums, *splitViewHorz, *splitComparative, *splitViewVert;
 CGFloat _splitViewVertDividerRatio;
}
@end
@implementation BrowserProbe
LAYOUT
TOGGLE
RESIZE
@end
static NSSplitView *split(BOOL vertical, CGFloat width, CGFloat height, NSUInteger count) {
 NSSplitView *v=[[NSSplitView alloc] initWithFrame:NSMakeRect(0,0,width,height)];
 v.vertical=vertical;
 for(NSUInteger i=0;i<count;i++){
   NSView *child=[[NSView alloc] initWithFrame:NSZeroRect];child.hidden=YES;[v addSubview:child];
 }
 return v;
}
static void visible(NSSplitView *v) {
 check(!v.hidden);
 for(NSView *child in v.subviews) {
   check(!child.hidden);check(child.frame.size.width>0);check(child.frame.size.height>0);
   check(NSContainsRect(v.bounds,child.frame));
 }
 for(NSUInteger i=1;i<v.subviews.count;i++) {
   NSRect previous=v.subviews[i-1].frame,current=v.subviews[i].frame;
   check(v.vertical ? NSMaxX(previous)<=NSMinX(current) : NSMaxY(previous)<=NSMinY(current));
 }
}
int main(void) { @autoreleasepool {
 [NSApplication sharedApplication];
 BrowserProbe *b=[BrowserProbe new];
 for(NSNumber *w in @[@640,@1600]) {
  b->splitDrawer=split(YES,w.doubleValue,600,2);b->splitDrawer.delegate=b;
  b->splitAlbums=split(NO,192,600,3);
  b->splitViewHorz=split(NO,w.doubleValue-192,600,2);
  b->splitComparative=split(YES,w.doubleValue-192,300,2);
  b->splitViewVert=split(YES,w.doubleValue-192,300,2);
  [NSUserDefaults.standardUserDefaults setBool:YES forKey:@"SplitDrawerHidden"];
  [NSUserDefaults.standardUserDefaults setBool:YES forKey:@"SplitComparativeHidden"];
  [b restoreWindowState:nil];
  for(NSSplitView *v in @[b->splitDrawer,b->splitAlbums,b->splitViewHorz,b->splitComparative,b->splitViewVert]) visible(v);
  check(b->splitDrawer.subviews[0].frame.size.width==192);
  check(![NSUserDefaults.standardUserDefaults boolForKey:@"SplitDrawerHidden"]);
  check(![NSUserDefaults.standardUserDefaults boolForKey:@"SplitComparativeHidden"]);
  NSSplitView *reloaded=split(YES,w.doubleValue,600,2);
  for(NSView *v in reloaded.subviews) v.hidden=NO;
  [reloaded restoreDefault:@"SplitDrawer"];visible(reloaded);
  check(reloaded.subviews[0].frame.size.width==192);
  [b drawerToggle:nil];check(b->splitDrawer.subviews[0].hidden);
  check(b->splitDrawer.subviews[0].frame.size.width==0);
  [b drawerToggle:nil];visible(b->splitDrawer);
  check(b->splitDrawer.subviews[0].frame.size.width==192);
  // Also recover a dragged-to-zero pane that was never marked hidden.
  b->splitDrawer.subviews[0].frame=NSZeroRect;
  [b drawerToggle:nil];visible(b->splitDrawer);
 }
 [b spaceEvenly:split(YES,0,0,0)];
 for(NSString *key in @[@"SplitDrawer",@"SplitAlbums",@"SplitHorz2",@"SplitComparative",@"SplitVert2",@"SplitDrawerHidden",@"SplitComparativeHidden"])
  [NSUserDefaults.standardUserDefaults removeObjectForKey:key];
 NSLog(@"PASS: horizontal/vertical hidden and collapsed panes, 640/1600 widths, toggle from zero, saved layout, visibility flags, empty split");
}}
'''.replace('LAYOUT', layout).replace('TOGGLE', toggle).replace('RESIZE', resize)
with tempfile.TemporaryDirectory(prefix='horos-layout-') as tmp:
    p = Path(tmp)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'AppKit',
                    '-I', str(root / 'Horos/Sources'), str(p / 'test.m'),
                    str(root / 'Horos/Sources/NSSplitViewSave.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
