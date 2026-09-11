#!/usr/bin/env python3
"""Validate bounded temporal wheel navigation from the production helper."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1];s=(root/'Horos/Sources/DCMView.m').read_bytes().decode('latin1')
a=s.index('static NSInteger HorosMovieIndexForScroll');b=s.index('- (void)scrollWheel:',a)
code=r'''
#import <Foundation/Foundation.h>
#include <math.h>
#include <float.h>
HELPER
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 check(HorosMovieIndexForScroll(0,4,-0.1)==1);
 check(HorosMovieIndexForScroll(0,4,0.1)==3);
 check(HorosMovieIndexForScroll(3,4,-2.5)==0);
 check(HorosMovieIndexForScroll(0,4,5)==2);
 for(int count=2;count<=100;count++)for(int i=0;i<count;i++)for(int d=-30;d<=30;d++){
  if(!d)continue;double step=d/-2.5;step=step>=0?ceil(step):floor(step);
  int expected=((i+(int)step)%count+count)%count;
  check(HorosMovieIndexForScroll(i,count,d)==expected);
 }
 // The former repeated float subtraction makes no progress at this magnitude.
 volatile float oldChange=FLT_MAX/2.5f;float after=oldChange-4;check(after==oldChange);
 for(int count=2;count<=100;count++){
  NSInteger pos=HorosMovieIndexForScroll(1,count,-FLT_MAX);
  NSInteger neg=HorosMovieIndexForScroll(1,count,FLT_MAX);
  check(pos>=0 && pos<count && neg>=0 && neg<count);
 }
 check(HorosMovieIndexForScroll(2,4,NAN)==2);
 check(HorosMovieIndexForScroll(2,4,INFINITY)==2);
 check(HorosMovieIndexForScroll(2,4,0)==2);
 check(HorosMovieIndexForScroll(2,0,1)==2);
 NSLog(@"PASS: temporal wrap, signed deltas, large finite events and invalid input");
}}
'''.replace('HELPER',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-movie-scroll-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-fsanitize=undefined,float-cast-overflow','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
