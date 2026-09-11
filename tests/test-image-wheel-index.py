#!/usr/bin/env python3
"""Exercise the production 2D wheel stepping branches under sanitizers."""
from pathlib import Path
import subprocess, sys, tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/DCMView.m']) if len(sys.argv)>1 else (root/'Horos/Sources/DCMView.m').read_bytes()).decode('latin1')
a=s.index('                else if( [theEvent modifierFlags]  & NSShiftKeyMask)',s.index('- (void)scrollWheel:'))
b=s.index('\n            }\n            else if( fabs( deltaX)',a)
branch=s[a:b].replace('else if(', 'if(',1)
a=s.index('            if( [self scrollThroughSeriesIfNecessary: curImage])',s.index('- (void)scrollWheel:'))
b=s.index("            if( listType == 'i')",a)
finish=s[a:b]
helper=''
if 'static short HorosImageIndexByAddingScroll' in s:
    a=s.index('static short HorosImageIndexByAddingScroll');b=s.index('static NSInteger HorosMovieIndexForScroll',a);helper=s[a:b]
code=r'''
#import <AppKit/AppKit.h>
#include <math.h>
#include <limits.h>
#include <float.h>
HELPER
@interface PluginManager:NSObject
+(BOOL)isComPACS;
@end
static BOOL compact;
@implementation PluginManager
+(BOOL)isComPACS{return compact;}
@end
@interface Pix:NSObject
@property int stack;
@end
@implementation Pix
@end
@interface Event:NSObject
@property NSUInteger modifierFlags;
@end
@implementation Event
@end
@interface View:NSObject {
@public short curImage, inc; int _imageRows,_imageColumns;
}
@property(retain) Pix *curDCM;
@property(retain) NSArray *dcmPixList;
-(void)finish;
-(void)step:(float)deltaY reverse:(float)reverseScrollWheel event:(Event*)theEvent;
@end
@implementation View
-(BOOL)scrollThroughSeriesIfNecessary:(int)i{return NO;}
-(void)finish { NSArray *dcmPixList=self.dcmPixList;
FINISH
}
-(void)step:(float)deltaY reverse:(float)reverseScrollWheel event:(Event*)theEvent {
BRANCH
}
@end
#define check(...) do {if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 View *v=[View new];v.curDCM=[Pix new];v.curDCM.stack=3;v->_imageRows=2;v->_imageColumns=2;
 Event*e=[Event new];
 for(int shift=0;shift<2;shift++)for(int rev=-1;rev<=1;rev+=2) {
  e.modifierFlags=shift?NSShiftKeyMask:0;
  for(int d=-30;d<=30;d++)if(d){
   v->curImage=100;float change=rev*d/2.5f;
   if(shift)change=change>=0?fmaxf(1,ceilf(change)):fminf(-1,floorf(change));
   else change=change>0?fmaxf(1,change):fminf(-1,change);
   short expected=(short)((shift?3:4)*change);
   [v step:d reverse:rev event:e];check(v->curImage==100+expected && v->inc==expected);
  }
  v->curImage=100;[v step:rev*1e12f reverse:rev event:e];check(v->curImage==SHRT_MAX && v->inc>0);
  v->curImage=100;[v step:-rev*1e12f reverse:rev event:e];check(v->curImage<0 && v->inc<0);
  v->curImage=SHRT_MAX-1;[v step:rev*5 reverse:rev event:e];check(v->curImage==SHRT_MAX && v->inc==1);
 }
 // Exercise the unchanged production clamp/wrap after the safe step.
 v->_imageRows=v->_imageColumns=1;e.modifierFlags=0;
 v.dcmPixList=@[@0,@1,@2,@3,@4,@5,@6,@7,@8,@9,@10,@11,@12,@13,@14,@15];
 for(int loop=0;loop<2;loop++) {
  [[NSUserDefaults standardUserDefaults] setBool:loop forKey:@"loopScrollWheel"];
  v->curImage=7;[v step:FLT_MAX reverse:1 event:e];[v finish];check(v->curImage==(loop?0:15));
  v->curImage=7;[v step:-FLT_MAX reverse:1 event:e];[v finish];check(v->curImage==(loop?15:0));
 }
 v->_imageRows=v->_imageColumns=2;
 compact=YES;e.modifierFlags=0;v->curImage=100;
 [v step:1e12f reverse:1 event:e];check(v->curImage==104 && v->inc==4);
 NSLog(@"PASS: ordinary/stack/ComPACS stepping, signed large deltas and short boundary direction");
}}
'''.replace('HELPER',helper).replace('BRANCH',branch).replace('FINISH',finish)
with tempfile.TemporaryDirectory(prefix='horos-wheel-index-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-Wno-deprecated-declarations','-fsanitize=undefined,float-cast-overflow','-fno-sanitize-recover=all','-framework','AppKit',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
