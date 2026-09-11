#!/usr/bin/env python3
"""Inject allocation failures into the actual production spline routine."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/ROI.m']) if len(sys.argv)>1 else (root/'Horos/Sources/ROI.m').read_bytes()).decode('latin1')
a=s.index('int spline(');b=s.index('@implementation ROI',a)
code=r'''
#import <Foundation/Foundation.h>
#include <assert.h>
#include <math.h>
static int failAt, calls, live;
static void *trackedMalloc(size_t size){if(++calls==failAt)return NULL;void*p=malloc(size);if(p)live++;return p;}
static void *trackedCalloc(size_t count,size_t size){if(++calls==failAt)return NULL;void*p=calloc(count,size);if(p)live++;return p;}
static void trackedFree(void*p){if(p)live--;free(p);}
#define malloc trackedMalloc
#define calloc trackedCalloc
#define free trackedFree
FUNCTION
#undef malloc
#undef calloc
#undef free
int main(){@autoreleasepool{
 NSPoint points[]={{0,0},{20,35},{45,-10},{60,15}};
 for(int segments=0;segments<2;segments++)for(int failure=1;failure<=12;failure++){
  calls=live=0;failAt=failure;NSPoint*out=NULL;long*map=NULL;
  int count=spline(points,4,&out,segments?&map:NULL,5);
  if(failure<=11+segments){assert(count==0);assert(out==NULL);assert(map==NULL);}
  else{assert(count>0);trackedFree(out);trackedFree(map);}
  assert(live==0);
 }
 calls=live=0;failAt=0;NSPoint*out=NULL;long*map=NULL;
 int count=spline(points,4,&out,&map,5);assert(count>4 && out && map);
 for(int i=0;i<count;i++){assert(isfinite(out[i].x)&&isfinite(out[i].y));assert(map[i]>=0&&map[i]<4);}
 trackedFree(out);trackedFree(map);assert(live==0);
 NSPoint duplicate[]={{0,0},{0,0},{10,10}};
 calls=live=0;failAt=0;out=NULL;map=NULL;
 assert(spline(duplicate,3,&out,&map,5)==0);
 assert(out==NULL && map==NULL && live==0);
 NSLog(@"PASS: all 12 allocation failures, clean output ownership and successful segment mapping");
}}
'''.replace('FUNCTION',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-spline-alloc-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=address,undefined','-fno-sanitize-recover=all','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
