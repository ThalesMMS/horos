#!/usr/bin/env python3
"""Check actual ROI spline/length code and text preparation independent of zoom."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/ROI.m']) if len(sys.argv)>1 else (root/'Horos/Sources/ROI.m').read_bytes()).decode('latin1')
def method(start):
 a=s.index(start);i=s.index('{',a)+1;depth=1
 while depth:
  depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
a=s.index('// TEXT',s.index('#pragma mark tCPolygon, tOPolygon, tAngle, tPencil'))
b=s.index('if( type == tCPolygon || type == tPencil)',a)
prepare=s[a:b]
a=s.index('for( int i = 0; i < (long)[splinePoints count]-1;',s.index('BOOL areaAvailable = YES;',b))
b=s.index('// The first and the last point',a)
loop=s[a:b]
a=s.index('float length = 0;',s.index('- (NSMutableDictionary*) dataString'))
b=s.index('[array setObject: [NSNumber numberWithFloat:length]',a)
export=s[a:b]
code=r'''
#import <Foundation/Foundation.h>
#include <math.h>
static int liveBuffers;
static void *trackedMalloc(size_t size){void*p=malloc(size);if(p)liveBuffers++;return p;}
static void *trackedCalloc(size_t count,size_t size){void*p=calloc(count,size);if(p)liveBuffers++;return p;}
static void trackedFree(void*p){if(p)liveBuffers--;free(p);}
#define malloc trackedMalloc
#define calloc trackedCalloc
#define free trackedFree
SPLINE
@interface MyPoint:NSObject
@property NSPoint point;
+(id)point:(NSPoint)p;
@end
@implementation MyPoint
+(id)point:(NSPoint)p{MyPoint*q=[MyPoint new];q.point=p;return [q autorelease];}
@end
typedef int ToolMode;
enum {tOPolygon=1,tCPolygon,tPencil,ROI_drawing};
@interface ROI:NSObject {
@public NSMutableArray *points;int type,mode;float pixelSpacingX,pixelSpacingY;
}
@property BOOL isSpline, isTextualDataDisplayed;
-(NSMutableArray*)points;
-(NSMutableArray*)splinePoints:(float)scale correspondingSegmentArray:(NSMutableArray**)array;
-(float)LengthFrom:(NSPoint)a to:(NSPoint)b inPixel:(BOOL)inPixel;
@end
@implementation ROI
-(NSMutableArray*)points{return points;}
METHODS
-(float)exportedLength {
 EXPORT
 return length;
}
-(float)displayedLengthAtZoom:(float)scaleValue {
 BOOL prepareTextualData=YES;
 NSMutableArray*splinePoints=[self splinePoints:scaleValue];
 PREPARE
 float length=0;
 LOOP
 return length;
}
@end
#undef malloc
#undef calloc
#undef free
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 ROI*r=[ROI new];r.isTextualDataDisplayed=YES;r->type=tOPolygon;r->pixelSpacingX=0.5;r->pixelSpacingY=2;
 r->points=[NSMutableArray arrayWithArray:@[[MyPoint point:NSMakePoint(0,0)],[MyPoint point:NSMakePoint(3,4)],[MyPoint point:NSMakePoint(6,4)]]];
 float expected=(hypot(1.5,8)+1.5)/10;
 for(NSNumber*z in @[@0.01,@1,@5])check(fabs([r displayedLengthAtZoom:z.floatValue]-expected)<1e-6);
 check(fabs([r exportedLength]-expected)<1e-6);
 r.isSpline=YES;
 r->points=[NSMutableArray arrayWithArray:@[[MyPoint point:NSMakePoint(0,0)],[MyPoint point:NSMakePoint(20,35)],[MyPoint point:NSMakePoint(45,-10)],[MyPoint point:NSMakePoint(60,15)]]];
 for(NSNumber*z in @[@0.01,@1,@5]){
  NSArray*sampled=[r splinePoints:z.floatValue];
  check(NSEqualPoints([(MyPoint*)sampled.firstObject point],[(MyPoint*)r->points.firstObject point]));
  check(NSEqualPoints([(MyPoint*)sampled.lastObject point],[(MyPoint*)r->points.lastObject point]));
 }
 check([[r splinePoints:0.01] count]!=[[r splinePoints:5] count]);
 for(int spacing=0;spacing<2;spacing++){
  r->pixelSpacingX=spacing?0.5:1;r->pixelSpacingY=spacing?2:1;
  float reference=[r displayedLengthAtZoom:5];
  check(fabs([r exportedLength]-reference)<1e-6);
  for(NSNumber*z in @[@0.01,@1,@5])check(fabs([r displayedLengthAtZoom:z.floatValue]-reference)<1e-6);
 }
 for(int i=0;i<100;i++){
  NSMutableArray*segments=nil;NSArray*sampled=[r splinePoints:5 correspondingSegmentArray:&segments];
  check(sampled.count==segments.count && sampled.count>4);
  check(liveBuffers==0);
 }
 r->type=tCPolygon;
 check(fabs([r exportedLength]-[r displayedLengthAtZoom:5])<1e-6);
 r.isSpline=NO;r->pixelSpacingX=.5;r->pixelSpacingY=2;
 r->points=[NSMutableArray arrayWithArray:@[[MyPoint point:NSMakePoint(0,0)],[MyPoint point:NSMakePoint(3,4)],[MyPoint point:NSMakePoint(6,4)]]];
 check(fabs([r exportedLength]-(hypot(1.5,8)+1.5+hypot(3,8))/10)<1e-6);
 r->points=[NSMutableArray array];check([r exportedLength]==0);
 [r->points addObject:[MyPoint point:NSMakePoint(2,3)]];check([r exportedLength]==0);
 NSLog(@"PASS: 1/100/500 percent zoom, curved splines and analytic anisotropic polyline");
}}
'''
parts={'SPLINE':s[s.index('int spline('):s.index('@implementation ROI')], 'METHODS':'\n'.join(method(m) for m in ['-(NSMutableArray*) splinePoints:(float) scale;','-(NSMutableArray*) splinePoints:(float) scale correspondingSegmentArray:','-(NSMutableArray*) splinePoints;','-(float) Length:','-(float) LengthFrom:']), 'PREPARE':prepare,'LOOP':loop,'EXPORT':export}
for k,v in parts.items():code=code.replace(k,v)
with tempfile.TemporaryDirectory(prefix='horos-roi-length-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fno-objc-arc','-Wno-incompatible-pointer-types','-fsanitize=undefined','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
