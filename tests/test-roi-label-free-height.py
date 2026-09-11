#!/usr/bin/env python3
"""Compile the production ROI height selection with real AppKit text metrics."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
s = (root/'Horos/Sources/ROI.m').read_bytes().decode('latin1')
a = s.index('- (NSArray*) fitTextualDataToAvailableSpace')
b = s.index('- (void) drawTextualData', a)
code = r'''
#import <Cocoa/Cocoa.h>
#import "Presentation-Swift.h"
static CGFloat fontHeight = 20;
@interface PeerWindow:NSObject
@property CGFloat backingScaleFactor;
@end
@implementation PeerWindow
@end
@interface PeerView:NSObject
@property(retain) PeerWindow *window;
@property NSRect drawingFrameRect;
@property(retain) NSArray *rectArray;
@end
@implementation PeerView
@end
@interface ROI:NSObject {
@public PeerView *curView; NSRect drawRect; NSArray *source;
}
-(NSArray*)renderedTextualLines;
-(long)maxStringWidth:(NSString*)text max:(long)width;
@end
@implementation ROI
-(NSArray*)renderedTextualLines{return source;}
-(long)maxStringWidth:(NSString*)text max:(long)width {
 if(!text.length) return width;
 CGFloat measured=[text sizeWithAttributes:@{NSFontAttributeName:[NSFont systemFontOfSize:12]}].width;
 return MAX(width, ceil((measured+8)*curView.window.backingScaleFactor));
}
METHOD
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 for(NSNumber *sf in @[@1,@2]) {
  CGFloat scale=sf.doubleValue;
  ROI *r=[ROI new]; r->curView=[PeerView new];r->curView.window=[PeerWindow new];r->curView.window.backingScaleFactor=scale;
  r->source=@[@"QA Height",@"",@"Line 01",@"Line 02",@"Line 03",@"Line 04",@"Value: 81",@"Coordinates"];
  r->drawRect=NSMakeRect(0,0,100,142);r->curView.drawingFrameRect=NSMakeRect(0,0,400*scale,200*scale);
  NSRect viewport=NSMakeRect(-200*scale,-100*scale,400*scale,200*scale);
  r->curView.rectArray=@[[NSValue valueWithRect:NSMakeRect(-200*scale,-100*scale,400*scale,60*scale)],
      [NSValue valueWithRect:NSMakeRect(-200*scale,40*scale,400*scale,60*scale)]];
  NSArray *limited=[r fitTextualDataToAvailableSpace];
  check(limited.count==3 && [limited.lastObject isEqual:@"…"]);
  check([limited[0] isEqual:@"QA Height"] && [limited[1] isEqual:@"Line 01"]);
  NSRect placed=[HorosROILabelPresentation placeLabelRect:NSOffsetRect(r->drawRect,8,8) inViewport:viewport avoiding:r->curView.rectArray];
  check(NSContainsRect(viewport,placed));
  for(NSValue *v in r->curView.rectArray)check(!NSIntersectsRect(placed,v.rectValue));
  // Removing annotations restores complete fields on the next layout.
  r->curView.rectArray=@[];
  check([[r fitTextualDataToAvailableSpace] isEqual:r->source]);
  check(r->drawRect.size.height==7*fontHeight*scale+2);
  // Completely occupied panes retain an explicit, minimum-size indicator.
  r->curView.rectArray=@[[NSValue valueWithRect:viewport]];
  check([[r fitTextualDataToAvailableSpace] isEqual:@[@"…"]]);
  check([r->source.lastObject isEqual:@"Coordinates"]);
 }
 NSLog(@"PASS: production ROI budget with actual font metrics, fixed bands, 1x/2x, full restoration and occupied-pane indication");
}}
'''.replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-free-height-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/ROILabelPresentation.swift'),'-emit-library','-module-name','Presentation','-emit-objc-header-path',str(p/'Presentation-Swift.h'),'-o',str(p/'libPresentation.dylib')],check=True)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Cocoa','-I',d,str(p/'test.m'),'-L',d,'-lPresentation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
