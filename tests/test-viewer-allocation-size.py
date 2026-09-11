#!/usr/bin/env python3
"""Exercise the production viewer allocation sizing block before malloc."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
helper=s[s.index('static BOOL HorosAccumulateImageMemory'):s.index('- (BOOL)computeEnoughMemory:')]
a=s.index('                    unsigned long long pixels = 0, padded = 0, bytes = 0, total = 0;')
b=s.index('                    testPtr[ x] = malloc',a)
code=r'''
#import <Foundation/Foundation.h>
#include <limits.h>
static int alerts;
static NSInteger NSRunInformationalAlertPanel(id a,id b,id c,id d,id e,...){alerts++;return 1;}
HELPER
static NSDictionary *size(NSArray *loadList,unsigned long mem){
 id curFile=loadList.firstObject;BOOL multiFrame=NO;unsigned long memBlock=0;
 BLOCK
 return @{@"pixels":@(memBlock),@"padded":@(mem),@"multi":@(multiFrame)};
}
static NSDictionary *image(long long w,long long h,long long f){return @{@"width":@(w),@"height":@(h),@"numberOfFrames":@(f),@"numberOfSeries":@1};}
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 check([size(@[image(32,32,1),image(32,32,1)],0)[@"pixels"] unsignedLongLongValue]==2*256*256);
 check([size(@[image(512,512,16)],0)[@"pixels"] unsignedLongLongValue]==512ULL*512*16);
 check([size(@[image(65536,65536,1)],0)[@"pixels"] unsignedLongLongValue]==65536ULL*65536);
 check([size(@[image(16,8192,1)],0)[@"pixels"] unsignedLongLongValue]==16*8192);
 check(size(@[image(LLONG_MAX,LLONG_MAX,1)],0)==nil);
 check(size(@[image(512,512,LLONG_MAX)],0)==nil);
 check(size(@[image(0,512,1)],0)==nil);
 check(size(@[image(-1,512,1)],0)==nil);
 check(size(@[image(512,512,1)],ULONG_MAX)==nil);
 check(alerts==5);
 NSLog(@"PASS: viewer sizing preserves small-image fallback and rejects invalid/overflowing allocations");
}}
'''.replace('HELPER',helper).replace('BLOCK',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-viewer-size-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-fsanitize=undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
