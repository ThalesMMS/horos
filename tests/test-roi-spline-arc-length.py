#!/usr/bin/env python3
"""Compare sampled production splines with numerical integration of their cubics."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/ROI.m']) if len(sys.argv)>1 else (root/'Horos/Sources/ROI.m').read_bytes()).decode('latin1')
f=s[s.index('int spline('):s.index('@implementation ROI')]
# Observe the computed coefficients without changing any production calculations.
marker='// compute points in this interval and display'
assert f.count(marker)==1
f=f.replace(marker,'reference += arc(bbx,ccx,ddx,bby,ccy,ddy,h[i],8192);\n referenceFine += arc(bbx,ccx,ddx,bby,ccy,ddy,h[i],16384);\n'+marker)
code=r'''
#import <Foundation/Foundation.h>
#include <math.h>
#include <assert.h>
static double sx,sy,reference,referenceFine;
static double speed(double t,double bx,double cx,double dx,double by,double cy,double dy){
 return hypot(sx*(bx+2*cx*t+3*dx*t*t),sy*(by+2*cy*t+3*dy*t*t));
}
static double arc(double bx,double cx,double dx,double by,double cy,double dy,double h,int n){
 double sum=0,step=h/n;
 for(int i=0;i<=n;i++)sum+=(i==0||i==n?1:i%2?4:2)*speed(i*step,bx,cx,dx,by,cy,dy);
 return sum*step/3;
}
FUNCTION
int main(){@autoreleasepool{
 NSPoint points[]={{5,5},{10,22},{20,7},{26,22},{5,5}};
 for(int closed=0;closed<2;closed++)for(int anisotropic=0;anisotropic<2;anisotropic++){
  sx=anisotropic?0.5:1;sy=anisotropic?2:1;reference=referenceFine=0;
  NSPoint*out=NULL;int count=spline(points,closed?5:4,&out,NULL,5);assert(count>4);
  double measured=0;for(int i=1;i<count;i++)measured+=hypot(sx*(out[i].x-out[i-1].x),sy*(out[i].y-out[i-1].y));
  free(out);
  NSLog(@"closed=%d anisotropic=%d sampled=%.9f mm integral=%.9f mm error=%.9f mm",closed,anisotropic,measured,referenceFine,fabs(measured-referenceFine));
  assert(fabs(reference-referenceFine)<1e-8);
  assert(fabs(measured-referenceFine)<0.01);
 }
}}
'''.replace('FUNCTION',f)
with tempfile.TemporaryDirectory(prefix='horos-spline-arc-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
