#!/usr/bin/env python3
"""Exercise production label placement including offscreen anchors/collisions."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
def read(name):
 path='Horos/Sources/'+name
 return (subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1' if name.endswith('.m') else 'utf8')
s=read('ROI.m');a=s.index('- (NSRect) findAnEmptySpaceForMyRect:');b=s.index('- (BOOL) isTextualDataDisplayed',a)
code=r'''
#import <Cocoa/Cocoa.h>
#import "Presentation-Swift.h"
@interface View:NSObject
@property NSRect drawingFrameRect;
@property(retain) NSMutableArray*rectArray;
@end
@implementation View
@end
@interface ROI:NSObject {@public View*curView;}
@end
@implementation ROI
METHOD
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 for(int scale=1;scale<=2;scale++)for(int columns=1;columns<=3;columns++){
  ROI*r=[ROI new];r->curView=[View new];NSRect frame=NSMakeRect(0,0,1200.0*scale/columns,800*scale);r->curView.drawingFrameRect=frame;
  NSRect viewport=NSMakeRect(-frame.size.width/2,-frame.size.height/2,frame.size.width,frame.size.height);
  for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int registry=0;registry<2;registry++){
   r->curView.rectArray=registry?[NSMutableArray array]:nil;BOOL moved=NO;
   NSRect input=NSMakeRect(x*3000,y*3000,150*scale,70*scale);
   NSRect placed=[r findAnEmptySpaceForMyRect:input :&moved];
   check(NSContainsRect(viewport,placed));check(NSEqualSizes(input.size,placed.size));
   if(x||y)check(moved);
   else check(!moved && placed.origin.x==8 && placed.origin.y==8);
  }
  r->curView.rectArray=[NSMutableArray arrayWithObject:[NSValue valueWithRect:viewport]];
  BOOL moved=NO;NSRect result=[r findAnEmptySpaceForMyRect:NSMakeRect(0,0,150*scale,70*scale) :&moved];
  check(NSContainsRect(viewport,result));
  check(NSEqualRects([r->curView.rectArray.lastObject rectValue],result));
  NSRect annotation=NSMakeRect(viewport.origin.x,NSMaxY(viewport)-100*scale,viewport.size.width,100*scale);
  r->curView.rectArray=[NSMutableArray arrayWithObject:[NSValue valueWithRect:annotation]];
  result=[r findAnEmptySpaceForMyRect:NSMakeRect(0,3000,150*scale,70*scale) :&moved];
  check(NSContainsRect(viewport,result) && !NSIntersectsRect(annotation,result));

 }
 for(int scale=1;scale<=2;scale++){
  ROI*r=[ROI new];r->curView=[View new];r->curView.drawingFrameRect=NSMakeRect(0,0,200*scale,200*scale);
  NSRect vertical=NSMakeRect(-10*scale,-100*scale,20*scale,200*scale);
  NSRect horizontal=NSMakeRect(-100*scale,-10*scale,200*scale,20*scale);
  r->curView.rectArray=[NSMutableArray arrayWithObjects:[NSValue valueWithRect:vertical],[NSValue valueWithRect:horizontal],nil];
  BOOL moved=NO;NSRect result=[r findAnEmptySpaceForMyRect:NSMakeRect(-8,-8,40*scale,40*scale) :&moved];
  check(!NSIntersectsRect(result,vertical) && !NSIntersectsRect(result,horizontal));
  check(NSContainsRect(NSMakeRect(-100*scale,-100*scale,200*scale,200*scale),result) && moved);
 }
 NSLog(@"PASS: all viewport edges, fully offscreen anchors, collision displacement, one/three panes, 1x/2x, absent registry and preserved size");
}}
'''.replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-label-viewport-') as d:
 p=Path(d);(p/'test.m').write_text(code);(p/'Presentation.swift').write_text(read('ROILabelPresentation.swift'))
 subprocess.run(['xcrun','swiftc',str(p/'Presentation.swift'),'-emit-library','-module-name','Presentation','-emit-objc-header-path',str(p/'Presentation-Swift.h'),'-o',str(p/'libPresentation.dylib')],check=True)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Cocoa','-I',d,str(p/'test.m'),'-L',d,'-lPresentation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
