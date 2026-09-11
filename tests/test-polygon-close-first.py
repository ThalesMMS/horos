#!/usr/bin/env python3
"""Exercise production polygon click handling and native hit tolerance."""
from pathlib import Path
import subprocess, sys, tempfile
root = Path(__file__).resolve().parents[1]
def source(file):
    path='Horos/Sources/'+file
    return (subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
s=source('ROI.m')
a=s.index('\telse\n\t{',s.index('//\telse if (type == tPencil)'))
b=s.index('\n- (BOOL)mouseRoiDown:',a)
body=s[a:b].replace('\telse\n','',1)
p=source('MyPoint.m');a=p.index('- (BOOL)isNearToPoint:');b=p.index('- (NSString*)description',a)
code=r'''
#import <Cocoa/Cocoa.h>
#define NEAR 5
@interface MyPoint:NSObject {NSPoint pt;}
-(id)initWithPoint:(NSPoint)p;
-(BOOL)isNearToPoint:(NSPoint)a :(float)scale :(float)ratio;
@end
@implementation MyPoint
-(id)initWithPoint:(NSPoint)p{if((self=[super init]))pt=p;return self;}
NEAR_METHOD
@end
@interface Pixel:NSObject
@property float pixelRatio;
@end
@implementation Pixel
@end
@interface View:NSObject
@property(retain) Pixel*curDCM;
@end
@implementation View
@end
enum{tCPolygon,tOPolygon,tAngle,tPencil,ROI_drawing,ROI_selected,ROI_selectedModify};
@interface ROI:NSObject {
@public NSMutableArray*points,*zPositions;int type,mode;float thickness;NSPoint clickPoint;View*curView;
}
-(BOOL)click:(NSPoint)pt scale:(float)scale backing:(float)backingScaleFactor;
@end
@implementation ROI
-(id)init{if((self=[super init])){points=[NSMutableArray new];zPositions=[NSMutableArray new];curView=[View new];curView.curDCM=[Pixel new];curView.curDCM.pixelRatio=1;thickness=1;type=tCPolygon;mode=ROI_drawing;}return self;}
-(BOOL)click:(NSPoint)pt scale:(float)scale backing:(float)backingScaleFactor {
 MyPoint*mypt;int slice=7;
BODY
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
int main(){@autoreleasepool{
 for(int backing=1;backing<=2;backing++)for(int zoom=1;zoom<=5;zoom+=4)for(int ratio=1;ratio<=2;ratio++){
  ROI*r=[ROI new];r->curView.curDCM.pixelRatio=ratio;
  float scale=zoom*backing;
  check([r click:NSMakePoint(0,0) scale:scale backing:backing]);
  check([r click:NSMakePoint(100,0) scale:scale backing:backing]);
  check([r click:NSMakePoint(100,100) scale:scale backing:backing]);
  check(![r click:NSMakePoint(4.0/zoom,4.0/(zoom*ratio)) scale:scale backing:backing]);
  check(r->mode==ROI_selected && r->points.count==3 && r->zPositions.count==3);
 }
 for(int scenario=0;scenario<5;scenario++){
  ROI*r=[ROI new];[r click:NSMakePoint(0,0) scale:1 backing:1];[r click:NSMakePoint(100,0) scale:1 backing:1];
  if(scenario!=0)[r click:NSMakePoint(100,100) scale:1 backing:1];
  if(scenario==1)r->type=tOPolygon;
  if(scenario==2)r->mode=ROI_selectedModify;
  NSPoint target=scenario==3?NSMakePoint(6,6):NSMakePoint(0,0);
  if(scenario==4)target=NSMakePoint(100,100);
  NSUInteger before=r->points.count;
  [r click:target scale:1 backing:1];
  if(scenario==4)check(r->mode==ROI_selected && r->points.count==before);
  else check(r->points.count==before+1);
 }
 NSLog(@"PASS: first-vertex completion, no duplicate points/slices, 1x/2x, zoom/anisotropy, minimum vertices, open/edit/outside hits, last-vertex completion");
}}
'''.replace('BODY',body).replace('NEAR_METHOD',p[a:b])
with tempfile.TemporaryDirectory(prefix='horos-polygon-close-') as d:
    p=Path(d);(p/'test.m').write_text(code)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Cocoa',str(p/'test.m'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
