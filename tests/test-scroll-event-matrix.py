#!/usr/bin/env python3
"""Run complete production wheel/drag handlers with controlled events and stacks.

No events are posted to the desktop. NSWindow/renderer/plugin side effects are
test doubles; preference policy, delta selection, index and sync logic are real.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
start = source.index('static short HorosImageIndexByAddingScroll')
wheel = source[start:source.index('\n- (void) otherMouseDown:', start)]
start = source.index('- (void)mouseDraggedImageScroll:')
drag = source[start:source.index('\n- (void)mouseDraggedBlending:', start)]
code = r'''
#import <AppKit/AppKit.h>
#import "Horos-Swift.h"
#include <limits.h>
#include <math.h>
@interface HorosPlanarPerformanceTrace:NSObject
-(uint64_t)beginScroll:(id)e fromIndex:(NSInteger)i;
-(void)endScroll:(uint64_t)s index:(NSInteger)i;
@end
@interface PluginManager:NSObject
+(BOOL)isComPACS;
@end
@implementation PluginManager
+(BOOL)isComPACS{return NO;}
@end
@interface TestWindow:NSObject
@end
@implementation TestWindow
-(BOOL)isVisible{return YES;}
-(BOOL)isMainWindow{return YES;}
-(void)makeKeyAndOrderFront:(id)sender{}
@end
@interface ViewerController:NSObject
@property NSInteger curMovieIndex;
+(BOOL)isFrontMost2DViewer:(id)w;
@end
@implementation ViewerController
+(BOOL)isFrontMost2DViewer:(id)w{return YES;}
-(BOOL)windowWillClose{return NO;}
-(NSInteger)maxMovieIndex{return 3;}
-(void)setMovieIndex:(NSInteger)i{self.curMovieIndex=i;}
-(void)adjustSlider{}
-(void)propagateSettings{}
-(void)windowDidBecomeMain:(id)n{}
@end
@interface Frame:NSObject
@property NSInteger ordinal, frameNumber, stack;
@property(retain) NSArray *position, *orientation;
@end
@implementation Frame
@end
@interface Event:NSObject
@property BOOL precise, inverted;
@property CGFloat dy, scrollY;
@property NSEventModifierFlags flags;
@end
@implementation Event
-(CGFloat)deltaY{return self.dy;}
-(CGFloat)deltaX{return 0;}
-(CGFloat)scrollingDeltaY{return self.scrollY;}
-(CGFloat)scrollingDeltaX{return 0;}
-(BOOL)hasPreciseScrollingDeltas{return self.precise;}
-(BOOL)isDirectionInvertedFromDevice{return self.inverted;}
-(NSEventModifierFlags)modifierFlags{return self.flags;}
@end
@interface DCMView:NSResponder {
@public short curImage,startImage; long scrollMode; NSPoint start,pointer,origin;
 NSArray *dcmPixList; char listType; NSMatrix *matrix; NSString *stringID;
 BOOL flippedData,drawing; int _imageRows,_imageColumns; id blendingView;
 float blendingFactor,scaleValue; NSInteger syncDelta;
}
@property NSRect frame;
@property(retain) TestWindow *window;
@property(retain) ViewerController *windowController;
@property(retain) HorosPlanarPerformanceTrace *horosPlanarPerformanceTrace;
@property(readonly) Frame *curDCM;
@end
@implementation DCMView
-(BOOL)is2DViewer{return YES;}
-(Frame*)curDCM{return dcmPixList[curImage];}
-(NSPoint)currentPointInView:(id)e{return pointer;}
-(void)setIndex:(short)i{curImage=i;}
-(void)setIndexWithReset:(short)i :(BOOL)b{curImage=i;}
-(void)sendSyncMessage:(NSInteger)i{syncDelta=i;}
-(BOOL)scrollThroughSeriesIfNecessary:(short)i{return NO;}
-(void)setBlendingFactor:(float)v{blendingFactor=v;}
-(void)setScaleValue:(float)v{scaleValue=v;}
-(void)setOriginX:(float)x Y:(float)y{origin=NSMakePoint(x,y);}
-(void)setNeedsDisplay:(BOOL)v{}
WHEEL
DRAG
@end
#define check(...) do { if(!(__VA_ARGS__)) { NSLog(@"FAIL %s",#__VA_ARGS__); return 1; } } while(0)
int main(){@autoreleasepool{
 check([NSEvent pressedMouseButtons]==0);
 NSUserDefaults *defaults=NSUserDefaults.standardUserDefaults;
 [defaults setBool:NO forKey:@"SelectWindowScrollWheel"];
 [defaults setBool:NO forKey:@"loopScrollWheel"];
 DCMView *v=[DCMView new];v.window=[TestWindow new];v.windowController=[ViewerController new];
 v->drawing=YES;v->listType='i';v->_imageRows=v->_imageColumns=1;
 v.frame=NSMakeRect(0,0,400,200);
 // Axial, coronal, sagittal and an oblique normal. Identifiers remain in
 // acquisition order; a reversed backing array must not reverse user intent.
 NSArray *normals=@[@[@0,@0,@1],@[@0,@1,@0],@[@1,@0,@0],@[@0.6,@0,@0.8]];
 NSUInteger scenarios=0,gestures=0;
 for(NSArray *normal in normals)for(int multi=0;multi<2;multi++)
 for(int flipped=0;flipped<2;flipped++)for(int natural=0;natural<2;natural++)
 for(int reversed=0;reversed<2;reversed++)for(int precise=0;precise<2;precise++){
  NSMutableArray *frames=[NSMutableArray array];
  for(int i=0;i<20;i++){
   Frame *f=[Frame new];f.ordinal=i;f.frameNumber=multi?i:0;f.stack=3;
   f.position=@[@([normal[0] doubleValue]*i),@([normal[1] doubleValue]*i),@([normal[2] doubleValue]*i)];
   f.orientation=normal;[frames addObject:f];
  }
  v->dcmPixList=flipped?frames.reverseObjectEnumerator.allObjects:frames;
  v->flippedData=flipped;
  [defaults setBool:reversed forKey:HorosScrollDirection.reversedPreferenceKey];
  for(int down=-1;down<=1;down+=2){
   v->curImage=10;NSInteger before=v.curDCM.ordinal;
   Event *event=[Event new];event.precise=precise;event.inverted=natural;
   CGFloat deviceY=-down*(natural?-1:1);
   // Opposite, much larger values in the unused accessor detect choosing the
   // wrong field. A test that sets both fields alike would miss that defect.
   event.dy=precise?deviceY:-deviceY*20;
   event.scrollY=precise?-deviceY*20:deviceY;
   [v scrollWheel:(NSEvent*)event];
   NSInteger expected=before+down*(reversed?1:-1);
   check(v.curDCM.ordinal==expected);
   check(v.curDCM.frameNumber==(multi?expected:0));
   for(int axis=0;axis<3;axis++)check(fabs([v.curDCM.position[axis] doubleValue]-expected*[normal[axis] doubleValue])<1e-12);
   check(v->syncDelta==v->curImage-10);gestures++;
   for(int axis=1;axis<=2;axis++){
    v->curImage=v->startImage=10;v->start=NSZeroPoint;v->scrollMode=axis;
    // Height and width differ by two. The matching movements both walk one
    // frame: five points vertically, ten points horizontally.
    v->pointer=axis==1?NSMakePoint(0,-5*down):NSMakePoint(10*down,0);
    [v mouseDraggedImageScroll:nil];check(v.curDCM.ordinal==expected);
    for(int component=0;component<3;component++)check(fabs([v.curDCM.position[component] doubleValue]-expected*[normal[component] doubleValue])<1e-12);
    check(v->syncDelta==v->curImage-10);gestures++;
   }
  }
  check([defaults boolForKey:HorosScrollDirection.reversedPreferenceKey]==reversed);
  scenarios++;
 }
 NSLog(@"PASS: %lu scenarios, %lu gestures; precise/classic accessor, natural/reverse/flipped, four acquisition normals, single/multiframe, both drag axes and sync deltas",(unsigned long)scenarios,(unsigned long)gestures);
}}
'''.replace('WHEEL',wheel).replace('DRAG',drag)
with tempfile.TemporaryDirectory(prefix='horos-scroll-events-') as directory:
    p = Path(directory); (p/'test.m').write_text(code)
    subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library','-module-name','Horos',
                    '-emit-objc-header','-emit-objc-header-path',str(p/'Horos-Swift.h'),'-c',
                    str(root/'Horos/Sources/ScrollDirection.swift'),'-o',str(p/'policy.o')],check=True)
    subprocess.run(['xcrun','clang','-c',str(p/'test.m'),'-o',str(p/'test.o'),'-I',str(p),
                    '-fno-objc-arc','-Wno-deprecated-declarations','-Wno-objc-method-access',
                    '-fsanitize=undefined,float-cast-overflow','-fno-sanitize-recover=all'],check=True)
    subprocess.run(['xcrun','swiftc',str(p/'policy.o'),str(p/'test.o'),'-framework','AppKit',
                    '-sanitize=undefined','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
