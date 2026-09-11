#!/usr/bin/env python3
"""Compile production point deletion and viewer removal branch with Cocoa/UBSan."""
from pathlib import Path
import subprocess, sys, tempfile
root=Path(__file__).resolve().parents[1]
def source(name):
    path='Horos/Sources/'+name
    return (subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
s=source('ROI.m');a=s.index('- (BOOL) deleteSelectedPoint');b=s.index('// in cm or in pixels',a);delete=s[a:b]
s=source('DCMView.m');a=s.index('                        if( [r deleteSelectedPoint] == NO');b=s.index('\n                    }',a);branch=s[a:b]
code=r'''
#import <Cocoa/Cocoa.h>
enum{tPlain,tText,t2DPoint,tOval,tROI,tMesure,tArrow,tCPolygon,tOPolygon,tPencil,tDynAngle,tAxis,tTAGT,ROI_drawing,ROI_selected,ROI_selectedModify};
NSString *OsirixROIChangeNotification=@"change",*OsirixRemoveROINotification=@"remove";
@interface ROI:NSObject {
@public BOOL hidden,locked;int type,mode;NSInteger selectedModifyPoint;NSRect rect;NSMutableArray *points,*zPositions;
}
@property BOOL locked;
-(BOOL)valid;
-(BOOL)deleteSelectedPoint;
-(double)groupID;
@end
@implementation ROI
@synthesize locked;
-(id)init {if((self=[super init])){points=[NSMutableArray new];zPositions=[NSMutableArray new];mode=ROI_drawing;type=tCPolygon;selectedModifyPoint=-1;}return self;}
-(BOOL)valid{return mode==ROI_drawing || points.count>=3;}
-(double)groupID{return 0;}
DELETE
@end
@interface View:NSObject {
@public ROI*curROI;BOOL drawingROI;NSMutableArray*rArray;
}
-(void)erase:(ROI*)r;
@end
@implementation View
-(void)deleteROIGroupID:(double)group{}
-(void)erase:(ROI*)r {long i=[rArray indexOfObjectIdenticalTo:r];double groupID;
BRANCH
}
@end
#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)
ROI*make(int count){ROI*r=[ROI new];for(int i=0;i<count;i++){[r->points addObject:@(i)];[r->zPositions addObject:@(10+i)];}return r;}
int main(){@autoreleasepool{
 for(int type=tCPolygon;type<=tPencil;type++){
  ROI*r=make(2);r->type=type;View*v=[View new];v->curROI=[r retain];v->drawingROI=YES;v->rArray=[NSMutableArray arrayWithObject:r];
  [v erase:r];check(r->points.count==1 && v->curROI==r && v->drawingROI && v->rArray.count==1);
  [v erase:r];check(r->points.count==0 && r->zPositions.count==0 && v->curROI==nil && !v->drawingROI && v->rArray.count==0);
  check(![r deleteSelectedPoint]);
 }
 ROI*r=make(4);r->mode=ROI_selectedModify;r->selectedModifyPoint=1;
 check([r deleteSelectedPoint]);check([r->points isEqual:@[@0,@2,@3]] && [r->zPositions isEqual:@[@10,@12,@13]]);
 r->selectedModifyPoint=999;check([r deleteSelectedPoint]);check(r->points.count==3);
 ROI*legacy=make(2);[legacy->zPositions removeAllObjects];check([legacy deleteSelectedPoint]);check(![legacy deleteSelectedPoint]);
 ROI*lockedROI=make(1);lockedROI.locked=YES;check(![lockedROI deleteSelectedPoint] && lockedROI->points.count==1);
 ROI*other=make(1);View*v=[View new];v->curROI=make(3);v->drawingROI=YES;v->rArray=[NSMutableArray arrayWithObjects:other,v->curROI,nil];[v erase:other];check(v->curROI!=nil && v->drawingROI && v->rArray.count==1);
 NSLog(@"PASS: empty drawing removal, viewer state, per-vertex slice positions, edit bounds, legacy positions, locked ROI and unrelated drawing");
}}
'''.replace('DELETE',delete).replace('BRANCH',branch)
with tempfile.TemporaryDirectory(prefix='horos-roi-cancel-') as d:
    p=Path(d);(p/'test.m').write_text(code)
    subprocess.run(['xcrun','clang','-fno-objc-arc','-fsanitize=undefined','-framework','Cocoa',str(p/'test.m'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
