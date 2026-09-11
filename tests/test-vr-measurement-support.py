#!/usr/bin/env python3
"""Exercise the real tool-selection guard and controller selection synchronization."""
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
def source(path):
    return (subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
s=source('Horos/Sources/VRView.mm')
a=s.index('- (void) setCurrentTool:(ToolMode) i\n{')
a=s.index('{',a)+1;b=s.index('ToolMode previousTool',a)
guard=s[a:b]
s=source('Horos/Sources/VRController.mm');a=s.index('    [view setCurrentTool: newTool];');b=s.index('\n}',a)
sync=s[a:b]
code=r'''
#import <AppKit/AppKit.h>
struct Camera {bool parallel;bool GetParallelProjection(){return parallel;}};
typedef NSInteger ToolMode;
enum {tMesure=1,t3DRotate=2,tWL=3};
static int alerts=0;
@interface TestAlert:NSObject
@property(copy) NSString *informativeText;
-(void)setAlertStyle:(NSAlertStyle)s;
-(void)setMessageText:(NSString*)s;
-(void)addButtonWithTitle:(NSString*)s;
-(NSInteger)runModal;
@end
@implementation TestAlert
-(void)setAlertStyle:(NSAlertStyle)s {}
-(void)setMessageText:(NSString*)s {}
-(void)addButtonWithTitle:(NSString*)s {}
-(NSInteger)runModal {assert([self.informativeText containsString:@"parallel projection"]);alerts++;return 1;}
@end
#define NSAlert TestAlert
@interface View:NSObject {
@public Camera *aCamera;ToolMode currentTool;
}
-(void)setCurrentTool:(ToolMode)i;
-(ToolMode)currentTool;
@end
@implementation View
-(void)setCurrentTool:(ToolMode)i { GUARD currentTool=i; }
-(ToolMode)currentTool {return currentTool;}
@end
@interface Controller:NSObject {
@public View *view;NSMatrix *toolsMatrix;
}
-(void)setCurrentTool:(ToolMode)newTool;
@end
@implementation Controller
-(void)setCurrentTool:(ToolMode)newTool { SYNC }
@end
int main(){@autoreleasepool{
 [NSApplication sharedApplication];Controller*c=[Controller new];c->view=[View new];
 c->toolsMatrix=[[NSMatrix alloc] initWithFrame:NSMakeRect(0,0,120,40) mode:NSRadioModeMatrix cellClass:[NSButtonCell class] numberOfRows:1 numberOfColumns:3];
 for(int i=0;i<3;i++)[[c->toolsMatrix cellAtRow:0 column:i] setTag:i+1];
 Camera camera={false};c->view->aCamera=&camera;c->view->currentTool=tWL;
 [c setCurrentTool:tMesure];
 if(c->view.currentTool!=tWL || [[c->toolsMatrix selectedCell] tag]!=tWL || alerts!=1){fprintf(stderr,"FAIL: perspective request bypassed guard or toolbar selection diverged\n");return 1;}
 camera.parallel=true;[c setCurrentTool:tMesure];assert(c->view.currentTool==tMesure && [[c->toolsMatrix selectedCell] tag]==tMesure && alerts==1);
 camera.parallel=false;[c setCurrentTool:t3DRotate];assert(c->view.currentTool==t3DRotate);
 [c setCurrentTool:tMesure];assert(c->view.currentTool==t3DRotate && [[c->toolsMatrix selectedCell] tag]==t3DRotate && alerts==2);
 puts("PASS: unsupported request explains restriction and preserves current tool/selection; parallel request succeeds");
}}
'''.replace('GUARD',guard).replace('SYNC',sync)
with tempfile.TemporaryDirectory(prefix='horos-vr-support-') as d:
    p=Path(d);(p/'test.mm').write_text(code)
    subprocess.run(['xcrun','clang++','-std=c++11','-Wno-deprecated-declarations','-framework','AppKit',str(p/'test.mm'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
