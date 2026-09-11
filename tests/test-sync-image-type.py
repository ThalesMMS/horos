#!/usr/bin/env python3
"""Test production nearest-plane selection with equal-position image types."""
from pathlib import Path
import subprocess,tempfile,sys,re
root=Path(__file__).resolve().parents[1]
s=subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/DCMView.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
a=s.index('+ (NSArray*)cleanedOutDcmPixArray:');b=s.index('\n- (void) drawOrientation:',a)
code=r'''
#import <Foundation/Foundation.h>
#include <math.h>
#define N2LogExceptionWithStackTrace(e) ((void)0)
@interface DCMPix:NSObject
@property(copy) NSString *imageType;
@property float z,sliceThickness;
-(void)orientation:(float*)v;-(void)origin:(float*)v;
@end
@implementation DCMPix
-(void)orientation:(float*)v{for(int i=0;i<9;i++)v[i]=0;v[0]=v[4]=v[8]=1;}
-(void)origin:(float*)v{v[0]=v[1]=0;v[2]=self.z;}
@end
@interface DCMView:NSObject { @public NSArray *dcmPixList,*cleanedOutDcmPixArray;int volumicData; }
@property(retain) DCMPix *curDCM;
+(float)angleBetweenVector:(float*)a andVector:(float*)b;
+(float)pbase_Plane:(float*)p :(float*)o :(float*)v :(float*)l;
-(int)findPlaneForPoint:(float*)p preferParallelTo:(float*)o localPoint:(float*)l distanceWithPlane:(float*)d preferImageType:(NSString*)t;
@end
@implementation DCMView
+(float)angleBetweenVector:(float*)a andVector:(float*)b{return 0;}
+(float)pbase_Plane:(float*)p :(float*)o :(float*)v :(float*)l{l[0]=p[0];l[1]=p[1];l[2]=o[2];return fabsf(p[2]-o[2]);}
METHODS
@end
static DCMPix *pix(NSString*t,float z){DCMPix*p=[DCMPix new];p.imageType=t;p.z=z;p.sliceThickness=1;return p;}
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 [[NSUserDefaults standardUserDefaults] setFloat:1 forKey:@"PARALLELPLANETOLERANCE"];
 DCMView*v=[DCMView new];v->volumicData=1;
 // Interleave types to exercise original array mapping and deterministic fallback.
 v->dcmPixList=@[pix(@"F",0),pix(@"W",0),pix(@"IP",0),pix(@"IP",1),pix(@"F",1),pix(@"W",1)];v.curDCM=v->dcmPixList[0];
 float p[3]={0,0,0},o[9]={1,0,0,0,1,0,0,0,1},distance;
 check([[DCMView cleanedOutDcmPixArray:v->dcmPixList] isEqual:v->dcmPixList]);
 for(NSString*t in @[@"F",@"W",@"IP"]){
  int i=[v findPlaneForPoint:p preferParallelTo:o localPoint:NULL distanceWithPlane:&distance preferImageType:t];
  check([[(DCMPix*)v->dcmPixList[i] imageType] isEqual:t] && distance==0);
 }
 check([v findPlaneForPoint:p preferParallelTo:o localPoint:NULL distanceWithPlane:NULL preferImageType:@"missing"]==0);
 check([v findPlaneForPoint:p preferParallelTo:o localPoint:NULL distanceWithPlane:NULL]==0);
 p[2]=1;check([v findPlaneForPoint:p preferParallelTo:o localPoint:NULL distanceWithPlane:NULL preferImageType:@"W"]==5);
 // Matching type on a farther plane must not override geometry.
 v->dcmPixList=@[pix(@"F",0),pix(@"W",1)];v->cleanedOutDcmPixArray=nil;p[2]=0;
 check([v findPlaneForPoint:p preferParallelTo:o localPoint:NULL distanceWithPlane:NULL preferImageType:@"W"]==0);
 p[2]=100;check([v findPlaneForPoint:p preferParallelTo:o localPoint:NULL distanceWithPlane:NULL preferImageType:@"W"]==-1);
 NSLog(@"PASS: equal-plane type preference, original indices, stable fallback and geometric priority");
}}
'''.replace('METHODS',s[a:b])
if len(sys.argv)>1:
    # Baseline has only the original spatial selector, which has no type input.
    code=re.sub(r' preferImageType:(?:t|@"[^"]*")', '', code)
    code=code.replace('check([[DCMView cleanedOutDcmPixArray:v->dcmPixList] isEqual:v->dcmPixList]);', '(void)0;')
with tempfile.TemporaryDirectory(prefix='horos-sync-type-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
