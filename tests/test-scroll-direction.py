#!/usr/bin/env python3
"""Wheel and click-drag walk the series the same way in every configuration."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
path='Horos/Sources/DCMView.m'
s=(subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')

wheel=s.index('- (void)scrollWheel:')
helper=s[s.index('static short HorosImageIndexByAddingScroll'):s.index('static NSInteger HorosMovieIndexForScroll')]
# The no-modifier branch is the second use of the shared sign inside scrollWheel.
first=s.index('float change = reverseScrollWheel * deltaY / 2.5f;',wheel)
start=s.index('float change = reverseScrollWheel * deltaY / 2.5f;',first+1)
branch=s[start:s.index('\n                }\n            }\n            else if( fabs( deltaX)',start)]
drag=s.index('- (void)mouseDraggedImageScroll:')
dragMethod=s[drag:s.index('\n- (void)mouseDraggedBlending:',drag)]

code=r'''
#import <AppKit/AppKit.h>
#import "Horos-Swift.h"
#include <limits.h>
#include <math.h>
HELPER
@interface PluginManager:NSObject
+(BOOL)isComPACS;
@end
@implementation PluginManager
+(BOOL)isComPACS{return NO;}
@end
@interface DCMView:NSObject {
@public short curImage,startImage;long scrollMode;NSPoint start;NSArray*dcmPixList;
       char listType;NSMatrix*matrix;NSString*stringID;BOOL flippedData;int _imageRows,_imageColumns;
       NSPoint pointer;
}
@property NSRect frame;
-(NSPoint)currentPointInView:(NSEvent*)e;
-(void)setIndex:(short)i;-(void)setIndexWithReset:(short)i :(BOOL)b;
-(BOOL)is2DViewer;-(id)windowController;-(void)adjustSlider;-(void)sendSyncMessage:(NSInteger)i;
-(short)wheelStepFrom:(short)from delta:(float)deltaY naturalScrolling:(BOOL)natural normalized:(BOOL)normalized;
-(short)dragStepFrom:(short)from verticalMove:(CGFloat)dy;
-(short)legacyDragStepFrom:(short)from verticalMove:(CGFloat)dy;
@end
@implementation DCMView
-(NSPoint)currentPointInView:(NSEvent*)e{return pointer;}
-(void)setIndex:(short)i{curImage=i;}-(void)setIndexWithReset:(short)i :(BOOL)b{curImage=i;}
-(BOOL)is2DViewer{return NO;}-(id)windowController{return nil;}-(void)adjustSlider{}
-(void)sendSyncMessage:(NSInteger)i{}
DRAG
-(short)wheelStepFrom:(short)from delta:(float)deltaY naturalScrolling:(BOOL)natural normalized:(BOOL)normalized {
 curImage=from;short inc=0;
 // macOS hands the app an already-inverted delta when natural scrolling is on.
 if(natural) deltaY = -deltaY;
 // scrollWheel: undoes that; passing NO reproduces the previous behaviour.
 if(normalized) deltaY *= [HorosScrollDirection deviceOrientationSignInverted: natural];
 float reverseScrollWheel = [HorosScrollDirection wheelSignForFlippedData: flippedData];
 BRANCH
 return curImage;
}
-(short)dragStepFrom:(short)from verticalMove:(CGFloat)dy {
 startImage=curImage=from;scrollMode=1;start=NSZeroPoint;pointer=NSMakePoint(0,dy);
 [self mouseDraggedImageScroll:nil];
 return curImage;
}
// The drag before the shared policy: neither the preference nor the flipped
// series order reached it.
-(short)legacyDragStepFrom:(short)from verticalMove:(CGFloat)dy {
 double movement = 0 - dy;
 double proposed = from + movement * (double)dcmPixList.count / (NSHeight(self.frame)/2.0);
 return (short)fmax(0, fmin(proposed, (double)dcmPixList.count-1));
}
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
static int sgn(int v){return v>0?1:(v<0?-1:0);}
int main(){@autoreleasepool{
 DCMView*v=[DCMView new];
 v->dcmPixList=@[@0,@1,@2,@3,@4,@5,@6,@7,@8,@9,@10,@11,@12,@13,@14,@15,@16,@17,@18,@19];
 v->_imageRows=v->_imageColumns=1;v.frame=NSMakeRect(0,0,100,200);v->listType='i';
 const short middle=10;
 int legacyDisagreements=0;BOOL legacyBrokeTheShippedDefault=NO;
 for(int natural=0;natural<2;natural++)
 for(int reversed=0;reversed<2;reversed++)for(int flipped=0;flipped<2;flipped++){
  [[NSUserDefaults standardUserDefaults] setBool:reversed
      forKey:HorosScrollDirection.reversedPreferenceKey];
  v->flippedData=flipped;

  // A gesture moving down: the wheel reports a negative deltaY with the system's
  // natural scrolling off, and the pointer moves to a smaller view y.
  int wheelIndexStep = [v wheelStepFrom:middle delta:-1.0f naturalScrolling:natural normalized:YES] - middle;
  int dragIndexStep  = [v dragStepFrom:middle verticalMove:-20] - middle;
  check(wheelIndexStep != 0 && dragIndexStep != 0);

  // With a flipped series the displayed slice moves opposite to the index.
  int displayedWheel = flipped ? -wheelIndexStep : wheelIndexStep;
  int displayedDrag  = flipped ? -dragIndexStep  : dragIndexStep;
  check(sgn(displayedWheel) == sgn(displayedDrag));

  // Down advances exactly when the reversal preference is on, whatever the
  // series order is.
  check(sgn(displayedWheel) == (reversed ? 1 : -1));

  // Upward gestures mirror the downward ones for both.
  check(sgn([v wheelStepFrom:middle delta:1.0f naturalScrolling:natural normalized:YES]-middle) == -sgn(wheelIndexStep));
  check(sgn([v dragStepFrom:middle verticalMove:20]-middle) == -sgn(dragIndexStep));

  int legacyDragIndex = [v legacyDragStepFrom:middle verticalMove:-20]-middle;
  int legacyWheelIndex = [v wheelStepFrom:middle delta:-1.0f naturalScrolling:natural normalized:NO]-middle;
  int legacyDragDisplayed  = flipped ? -legacyDragIndex  : legacyDragIndex;
  int legacyWheelDisplayed = flipped ? -legacyWheelIndex : legacyWheelIndex;
  if(sgn(legacyDragDisplayed) != sgn(legacyWheelDisplayed)) {
   legacyDisagreements++;
   // The macOS default (natural scrolling on) with the shipped Horos default
   // (preference on) was one of the broken configurations.
   if(natural && reversed && !flipped) legacyBrokeTheShippedDefault=YES;
  }
 }
 // Before the shared policy the drag ignored both inputs and the wheel followed
 // the system setting, so half of the eight configurations were inverted —
 // including the shipped one, natural scrolling on with the preference on.
 check(legacyDisagreements==4);
 check(legacyBrokeTheShippedDefault);

 // Sensitivity still comes from the matching axis, and the clamps still hold.
 [[NSUserDefaults standardUserDefaults] setBool:YES
     forKey:HorosScrollDirection.reversedPreferenceKey];
 v->flippedData=NO;
 // One frame, both axes: vertical sensitivity comes from the height and
 // horizontal from the width, so the same 20 point drag moves different amounts.
 v.frame=NSMakeRect(0,0,400,200);
 check([v dragStepFrom:middle verticalMove:-20]==middle+4);   // 20 of a 100 point half-height
 v->startImage=v->curImage=middle;v->scrollMode=2;v->start=NSZeroPoint;
 v->pointer=NSMakePoint(20,0);[v mouseDraggedImageScroll:nil];
 check(v->curImage==middle+2);                                // 20 of a 200 point half-width
 check([v dragStepFrom:middle verticalMove:-1e12]==19);
 check([v dragStepFrom:middle verticalMove:1e12]==0);
 check([v dragStepFrom:middle verticalMove:NAN]==middle);
 NSLog(@"PASS: wheel and drag agree in all eight natural/preference/flipped combinations, half of which used to disagree; axis sensitivity and clamps preserved");
}}
'''.replace('HELPER',helper).replace('BRANCH',branch).replace('DRAG',dragMethod)

with tempfile.TemporaryDirectory(prefix='horos-scroll-direction-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library','-module-name','Horos',
   '-emit-objc-header','-emit-objc-header-path',str(p/'Horos-Swift.h'),
   '-c',str(root/'Horos/Sources/ScrollDirection.swift'),'-o',str(p/'scroll.o')],check=True)
 subprocess.run(['xcrun','clang','-c',str(p/'test.m'),'-o',str(p/'test.o'),'-I',str(p),
   '-fno-objc-arc','-Wno-deprecated-declarations','-fsanitize=undefined,float-cast-overflow',
   '-fno-sanitize-recover=all'],check=True)
 subprocess.run(['xcrun','swiftc',str(p/'scroll.o'),str(p/'test.o'),'-o',str(p/'test'),
   '-framework','AppKit','-sanitize=undefined'],check=True)
 subprocess.run([str(p/'test')],check=True)
