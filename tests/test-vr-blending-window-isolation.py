#!/usr/bin/env python3
"""Exercise production blended windowing without mutating primary WL/WW."""
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
path='Horos/Sources/VRView.mm'
s=(subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
a=s.index('            case tWLBlended:',s.index('- (void)mouseDragged:'))
b=s.index('            case tWL:',a)
block=s[a:b].replace('case tWLBlended:', 'case 0:')
code=r'''
#import <Cocoa/Cocoa.h>
#include <cmath>
static NSInteger mode;
@interface TestDefaults:NSObject
+ (id)standardUserDefaults;
- (NSInteger)integerForKey:(NSString *)key;
- (BOOL)boolForKey:(NSString *)key;
@end
@implementation TestDefaults
+ (id)standardUserDefaults { return [[[self alloc] init] autorelease]; }
- (NSInteger)integerForKey:(NSString *)key { return [key isEqualToString:@"PETWindowingMode"]?mode:0; }
- (BOOL)boolForKey:(NSString *)key { return YES; }
@end
#define NSUserDefaults TestDefaults
@interface Event:NSObject { @public double dx,dy; }
- (double)deltaX; - (double)deltaY;
@end
@implementation Event
- (double)deltaX {return dx;} - (double)deltaY {return dy;}
@end
@interface Controller:NSObject { @public NSString *kind; }
- (id)blendingController; - (NSString *)modality;
@end
@implementation Controller
- (id)blendingController {return self;} - (NSString *)modality {return kind;}
@end
@interface Harness:NSObject { @public float wl,ww,blendingWl,blendingWw; Controller *controller; }
- (void)apply:(Event *)theEvent;
@end
@implementation Harness
- (void)setBlendingWLWW:(float)level :(float)width { blendingWl=level;blendingWw=width; }
- (void)setNeedsDisplay:(BOOL)value {}
- (void)apply:(Event *)theEvent {
 float _startWW,_startWL,_startMin,_startMax,WWAdapter,endlevel,startlevel;
 switch(0) { BLOCK }
}
@end
int main(){ @autoreleasepool {
 int count=0;
 for(NSString *modality in @[@"PT",@"NM",@"CT"])for(mode=0;mode<3;mode++)for(int drag=0;drag<4;drag++) {
  Controller *controller=[Controller new];controller->kind=modality;
  Harness *h=[Harness new];h->controller=controller;h->wl=150;h->ww=1000;h->blendingWl=50;h->blendingWw=100;
  Event *event=[Event new];event->dx=drag==1?20:drag==3?-200:0;event->dy=drag==1?10:drag==2?200:0;
  [h apply:event];
  if(h->wl!=150 || h->ww!=1000){fprintf(stderr,"FAIL: %s mode %ld drag %d changed primary WL/WW to %g/%g\n",modality.UTF8String,(long)mode,drag,h->wl,h->ww);return 1;}
  if(!std::isfinite(h->blendingWl)||h->blendingWw<.09999)return 2;
  if(![modality isEqualToString:@"CT"] && mode>0 && h->blendingWl-h->blendingWw/2 < -1e-6)return 3;
  if(drag==0 && (h->blendingWl!=50 || h->blendingWw!=100))return 4;
  [event release];[h release];[controller release];count++;
 }
 printf("PASS: %d production blended-window cases preserve primary WL/WW, width limits and PET/NM lower bounds\n",count);
}}
'''.replace('BLOCK',block)
with tempfile.TemporaryDirectory(prefix='horos-vr-window-') as d:
    p=Path(d);(p/'test.mm').write_text(code)
    subprocess.run(['xcrun','clang++','-std=c++11',str(p/'test.mm'),'-framework','Cocoa','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
