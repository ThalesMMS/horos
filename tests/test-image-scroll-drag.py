#!/usr/bin/env python3
"""Run production drag navigation with controlled geometry and pointer positions."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/DCMView.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
a=s.index('- (void)mouseDraggedImageScroll:');b=s.index('\n- (void)mouseDraggedBlending:',a)
code=r'''
#import <AppKit/AppKit.h>
#import "Horos-Swift.h"
#include <limits.h>
#include <math.h>
@interface DCMView:NSObject { @public short curImage,startImage;long scrollMode;NSPoint start,current;NSArray*dcmPixList;char listType;NSMatrix*matrix;NSString*stringID;NSInteger syncDelta;BOOL flippedData; }
@property NSRect frame;
-(NSPoint)currentPointInView:(NSEvent*)e;
-(void)setIndex:(short)i;-(void)setIndexWithReset:(short)i :(BOOL)b;
-(BOOL)is2DViewer;-(id)windowController;-(void)adjustSlider;-(void)sendSyncMessage:(NSInteger)i;
@end
@implementation DCMView
-(NSPoint)currentPointInView:(NSEvent*)e{return current;}
-(void)setIndex:(short)i{curImage=i;}-(void)setIndexWithReset:(short)i :(BOOL)b{curImage=i;}
-(BOOL)is2DViewer{return NO;}-(id)windowController{return nil;}-(void)adjustSlider{}
-(void)sendSyncMessage:(NSInteger)i{syncDelta=i;}
METHOD
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 // Direction now comes from the shared policy; pin it to the shipped default so
 // these geometry expectations stay comparable with the historical ones.
 [[NSUserDefaults standardUserDefaults] setBool:YES
     forKey:HorosScrollDirection.reversedPreferenceKey];
 DCMView*v=[DCMView new];v->dcmPixList=@[@0,@1,@2,@3,@4,@5,@6,@7,@8,@9];v->startImage=v->curImage=5;v->start=NSZeroPoint;v.frame=NSMakeRect(0,0,100,200);
 v->scrollMode=1;v->current=NSMakePoint(0,-20);[v mouseDraggedImageScroll:nil];check(v->curImage==7 && v->syncDelta==2);
 v->scrollMode=2;v->current=NSMakePoint(20,0);[v mouseDraggedImageScroll:nil];check(v->curImage==9);
 v->current=NSMakePoint(1e12,0);[v mouseDraggedImageScroll:nil];check(v->curImage==9);
 v->current=NSMakePoint(-1e12,0);[v mouseDraggedImageScroll:nil];check(v->curImage==0);
 v->curImage=5;v.frame=NSZeroRect;v->current=NSMakePoint(20,0);[v mouseDraggedImageScroll:nil];check(v->curImage==5);
 v.frame=NSMakeRect(0,0,100,200);v->current=NSMakePoint(NAN,0);[v mouseDraggedImageScroll:nil];check(v->curImage==5);
 v->current=NSMakePoint(10,0);v->dcmPixList=@[];[v mouseDraggedImageScroll:nil];check(v->curImage==5);
 NSLog(@"PASS: axis-specific sensitivity, large drags, empty lists and invalid geometry");
}}
'''.replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-drag-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library','-module-name','Horos',
   '-emit-objc-header','-emit-objc-header-path',str(p/'Horos-Swift.h'),
   '-c',str(root/'Horos/Sources/ScrollDirection.swift'),'-o',str(p/'scroll.o')],check=True)
 subprocess.run(['xcrun','clang','-c',str(p/'test.m'),'-o',str(p/'test.o'),'-I',str(p),
   '-fobjc-arc','-fsanitize=undefined,float-cast-overflow'],check=True)
 subprocess.run(['xcrun','swiftc',str(p/'scroll.o'),str(p/'test.o'),'-o',str(p/'test'),
   '-framework','AppKit','-sanitize=undefined'],check=True)
 subprocess.run([str(p/'test')],check=True)
