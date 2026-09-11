#!/usr/bin/env python3
"""Validate Swift median and its production DCMPix statistics integration."""
from pathlib import Path
import subprocess, sys, tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/DCMPix.m']) if len(sys.argv)>1 else (root/'Horos/Sources/DCMPix.m').read_bytes()).decode('latin1')
a=s.index('- (void) computeROI:(ROI*) roi :(float*) mean :(float *)total :(float *)dev :(float *)min :(float *)max :(float *)skewness')
b=s.index('- (void) setRGB:',a)
r=(root/'Horos/Sources/ROI.m').read_bytes().decode('latin1')
label=next(line.split('self.textualBoxLine3 = ',1)[1].strip() for line in r.splitlines() if 'self.textualBoxLine3 =' in line and 'Median:' in line)
ea=r.index('            [array setObject:@(isfinite(self.median))')
eb=r.index('\n',r.index('forKey:@"MedianUnit"]',ea))
tabular=next(line.strip() for line in r.splitlines() if 'return [NSString stringWithFormat:' in line and ', name, mean, min, max, total, dev,' in line)
code=r'''
#import <Cocoa/Cocoa.h>
#import "Statistics-Swift.h"
@interface PixelUnit:NSObject
@property BOOL SUVConverted;
@property(copy) NSString*rescaleType;
@end
@implementation PixelUnit
@end
@interface ROI:NSObject
@property double median;
@property(copy) NSArray<NSNumber*> *samples;
@property(retain) PixelUnit*pix;
-(NSString*)labelWithUnit:(NSString*)pixelUnit;
-(NSDictionary*)summary;
-(NSString*)tabular;
@end
@implementation ROI
-(NSString*)tabular{
 NSString*name=@"QA";float mean=1,min=0,max=2,total=3,dev=4;PixelUnit*pix=self.pix;
 TABULAR
}
-(NSString*)labelWithUnit:(NSString*)pixelUnit{
 float rmean=1,rdev=2,rtotal=3;
 return LABEL
}
-(NSDictionary*)summary{
 NSMutableDictionary*array=[NSMutableDictionary dictionary];
 EXPORT
 return array;
}
@end
@interface DCMPix:NSObject
-(float*)getROIValue:(long*)count :(ROI*)roi :(void*)unused;
+(float)kurtosis:(float*)v length:(long)n mean:(double)m;
+(float)skewness:(float*)v length:(long)n mean:(double)m;
@end
@implementation DCMPix
-(float*)getROIValue:(long*)count :(ROI*)roi :(void*)unused {
 *count=roi.samples.count;if(!*count)return NULL;
 float*v=malloc(*count*sizeof(float));for(long i=0;i<*count;i++)v[i]=roi.samples[i].floatValue;return v;
}
+(float)kurtosis:(float*)v length:(long)n mean:(double)m{return 0;}
+(float)skewness:(float*)v length:(long)n mean:(double)m{return 0;}
METHOD
@end
static int failures;
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);failures++;}}while(0)
int main(){@autoreleasepool{
 NSArray *samples=@[@[@9,@1,@5],@[@9,@1,@5,@3],@[],@[@42],@[@(-9),@(-1),@(-5)],@[@(NAN),@1,@3,@(INFINITY)],@[@(NAN),@(-INFINITY)],@[@(FLT_MAX),@(FLT_MAX)]];
 double expected[]={5,4,NAN,42,-5,2,NAN,FLT_MAX};
 for(NSUInteger i=0;i<samples.count;i++){
  ROI*r=[ROI new];r.samples=samples[i];DCMPix*p=[DCMPix new];
  float mean,total,dev,min,max;
  [p computeROI:r :&mean :&total :&dev :&min :&max :NULL :NULL];
  check(isnan(expected[i])?isnan(r.median):r.median==expected[i]);
  if(i==0)check(mean==5 && total==15 && dev==4 && min==1 && max==9);
  if(i==1)check(mean==4.5 && total==18 && fabs(dev-sqrt(35.0/3))<1e-6 && min==1 && max==9);
  if(i==2 || i==3)check(dev==0 && !signbit(dev));
 }
 for(NSNumber*scale in @[@(2e38f),@(1e-30f)]){
  ROI*r=[ROI new];r.samples=@[@(-scale.floatValue),scale];
  DCMPix*p=[DCMPix new];float dev;
  [p computeROI:r :NULL :NULL :&dev :NULL :NULL :NULL :NULL];
  double expectedDev=sqrt(2.0)*scale.doubleValue;
  check(isfinite(dev) && fabs(dev/expectedDev-1)<1e-6);
 }
 for(NSNumber*invalid in @[@(NAN),@(INFINITY)]){
  ROI*r=[ROI new];r.samples=@[invalid];DCMPix*p=[DCMPix new];float dev;
  [p computeROI:r :NULL :NULL :&dev :NULL :NULL :NULL :NULL];
  check(isnan(dev));
 }
 float input[]={9,1,5,3};
 check([HorosROIStatistics medianOfValues:input count:4]==4);
 check(input[0]==9 && input[1]==1 && input[2]==5 && input[3]==3);
 check(isnan([HorosROIStatistics medianOfValues:NULL count:0]));
 check(isnan([HorosROIStatistics medianOfValues:input count:-1]));
 ROI*r=[ROI new];r.pix=[PixelUnit new];r.pix.rescaleType=@"HU";r.median=4;
 check([[r labelWithUnit:@" HU "] containsString:@"Median: 4.000 HU"]);
 check([[r summary][@"MedianUnit"] isEqual:@"HU"] && [[r summary][@"Median"] doubleValue]==4);
 check([[r tabular] isEqual:@"QA\t1.000\t0.000\t2.000\t3.000\t4.000\t4.000\tHU"]);
 r.pix.SUVConverted=YES;check([[r summary][@"MedianUnit"] isEqual:@"SUV"]);
 r.median=NAN;
 check([[r labelWithUnit:@" HU "] containsString:@"Median: N/A HU"]);
 check(![[r summary][@"MedianAvailable"] boolValue] && ![r summary][@"Median"]);
 check([[r tabular] hasSuffix:@"\tN/A\tSUV"]);
 if(failures)return 1;
 NSLog(@"PASS: median, metadata/clipboard, zero/singleton dispersion, wide-range deviation and unchanged ordinary statistics");
}}
'''.replace('METHOD',s[a:b]).replace('LABEL',label).replace('EXPORT',r[ea:eb]).replace('TABULAR',tabular)
with tempfile.TemporaryDirectory(prefix='horos-roi-median-') as d:
    p=Path(d);(p/'test.m').write_text(code)
    subprocess.run(['xcrun','swiftc',str(root/'Horos/Sources/ROIStatistics.swift'),'-emit-library','-module-name','Statistics','-emit-objc-header-path',str(p/'Statistics-Swift.h'),'-o',str(p/'libStatistics.dylib')],check=True)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Cocoa','-I',d,str(p/'test.m'),'-L',d,'-lStatistics','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
