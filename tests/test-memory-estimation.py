#!/usr/bin/env python3
"""Run the real estimator with bounded allocation probes and controlled failures."""
from pathlib import Path
import subprocess,tempfile,sys,os
root=Path(__file__).resolve().parents[1]
s=subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
a=s.index('- (BOOL)computeEnoughMemory:');b=s.index('\n- (ViewerController*) openViewerFromImages:',a)
helper=s[s.index('static BOOL HorosAccumulateImageMemory'):a] if 'static BOOL HorosAccumulateImageMemory' in s else ''
code=r'''
#import <Foundation/Foundation.h>
#include <limits.h>
#define NSManagedObject NSObject
static int live, calls, failAt, operations;
static size_t largest;
static void *probeMalloc(size_t n){calls++;largest=MAX(largest,n);if(calls==failAt)return NULL;live++;return malloc(1);}
static void *probeCalloc(size_t n,size_t s){calls++;if(calls==failAt)return NULL;void*p=calloc(n,s);if(p)live++;return p;}
static void probeFree(void*p){if(p){live--;free(p);}}
@interface NSThread(Test)
@property NSString *status;
@property double progress;
-(void)enterOperation;-(void)exitOperation;
@end
@implementation NSThread(Test)
-(void)setStatus:(NSString*)s{} -(NSString*)status{return nil;}
-(void)setProgress:(double)p{} -(double)progress{return 0;}
-(void)enterOperation{operations++;} -(void)exitOperation{operations--;}
@end
@interface Browser:NSObject
-(BOOL)computeEnoughMemory:(NSArray*)a :(unsigned long*)m;
@end
HELPER
#define malloc probeMalloc
#define calloc probeCalloc
#define free probeFree
@implementation Browser
METHOD
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);exit(1);}}while(0)
static NSDictionary *image(long long w,long long h,long long f){return @{@"width":@(w),@"height":@(h),@"numberOfFrames":@(f),@"numberOfSeries":@1};}
int main(int argc,char**argv){@autoreleasepool{
 Browser*b=[Browser new];unsigned long m=99;
 NSMutableArray *many=[NSMutableArray array];for(int i=0;i<1001;i++)[many addObject:@[]];
 if(argc>1){check([b computeEnoughMemory:many :&m]);return 0;}
 check([b computeEnoughMemory:@[] :&m] && m==0 && live==0);
 check([b computeEnoughMemory:@[@[image(1024,1024,16)]] :&m] && m==64 && live==0);
 check([b computeEnoughMemory:many :&m] && live==0);
 largest=0;check([b computeEnoughMemory:@[@[image(65536,65536,1)]] :&m]);check(largest>16ULL*1024*1024*1024 && m>=16384);
 check(![b computeEnoughMemory:@[@[image(LLONG_MAX,LLONG_MAX,2)]] :&m] && live==0);
 check(![b computeEnoughMemory:@[@[image(0,512,1)]] :&m] && live==0);
 check(![b computeEnoughMemory:@[@[image(-1,512,1)]] :&m] && live==0);
 calls=0;failAt=1;check(![b computeEnoughMemory:@[@[image(512,512,1)]] :&m] && live==0);
 calls=0;failAt=3;check(![b computeEnoughMemory:@[@[image(512,512,1)],@[image(512,512,1)],@[image(512,512,1)]] :&m] && live==0);failAt=0;
 @try{[b computeEnoughMemory:@[@[image(512,512,1)],@[[NSObject new]]] :&m];check(NO);} @catch(NSException*e){}
 check(live==0 && operations==0);
 NSLog(@"PASS: 1001 series, float-byte estimates, wide dimensions, overflow/invalid metadata, failed probes and exception cleanup");
}}
'''.replace('HELPER',helper).replace('METHOD',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-memory-estimate-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-fsanitize=address,undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
 subprocess.run([str(p/'test')]+sys.argv[2:],check=True,env=env)
