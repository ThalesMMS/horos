#!/usr/bin/env python3
"""Run the production fusion command with controlled viewer identities and geometry."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
path='Horos/Sources/ViewerController.m'
s=(subprocess.check_output(['git','show',sys.argv[1]+':'+path]) if len(sys.argv)>1 else (root/path).read_bytes()).decode('latin1')
a=s.index('-(IBAction) blendWindows:');b=s.index('-(void) ActivateBlending:',a)
code=r'''
#import <Cocoa/Cocoa.h>
#include <assert.h>
static NSMutableArray *viewers;
static int alerts;
#define NSRunCriticalAlertPanel(...) (++alerts)
@interface Geometry:NSObject { @public BOOL tilted; }
- (void)orientation:(float *)out;
@end
@implementation Geometry
- (void)orientation:(float *)out { memset(out,0,9*sizeof(float));out[tilted?6:8]=1; }
@end
@interface Image:NSObject { @public Geometry *geometry; }
- (id)curDCM; - (void)sendSyncMessage:(int)value;
@end
@implementation Image
- (id)curDCM {return geometry;} - (void)sendSyncMessage:(int)value {}
@end
@interface DCMView:NSObject
+ (float)angleBetweenVector:(float *)a andVector:(float *)b;
@end
@implementation DCMView
+ (float)angleBetweenVector:(float *)a andVector:(float *)b { return a[2]==b[2]?0:90; }
@end
@interface Preferences:NSObject
+ (id)standardUserDefaults; - (float)floatForKey:(NSString *)key;
@end
@implementation Preferences
+ (id)standardUserDefaults {return [[[self alloc] init] autorelease];}
- (float)floatForKey:(NSString *)key {return .01;}
@end
#define NSUserDefaults Preferences
@interface ViewerController:NSObject {
@public ViewerController *blendingController; NSString *kind,*study; Image *image; BOOL gantry;
}
+ (NSMutableArray *)getDisplayed2DViewers;
- (id)blendingController; - (void)ActivateBlending:(ViewerController *)other;
- (NSString *)modality; - (NSString *)studyInstanceUID; - (id)imageView; - (BOOL)isGantryTitled;
- (void)blendWindows:(id)sender;
@end
@implementation ViewerController
+ (NSMutableArray *)getDisplayed2DViewers {return viewers;}
- (id)blendingController {return blendingController;}
- (void)ActivateBlending:(ViewerController *)other {blendingController=other;}
- (NSString *)modality {return kind;} - (NSString *)studyInstanceUID {return study;}
- (id)imageView {return image;} - (BOOL)isGantryTitled {return gantry;}
COMMAND
@end
ViewerController *make(NSString *kind,NSString *study) {
 ViewerController *v=[[[ViewerController alloc] init] autorelease];v->kind=kind;v->study=study;
 v->image=[[[Image alloc] init] autorelease];v->image->geometry=[[[Geometry alloc] init] autorelease];[viewers addObject:v];return v;
}
int main(){@autoreleasepool {
 viewers=[NSMutableArray array];
 ViewerController *ct=make(@"CT",@"A"),*pt=make(@"PT",@"A"),*ct2=make(@"CT",@"B"),*pt2=make(@"NM",@"B");
 ct->blendingController=pt;ct2->blendingController=pt2;
 [pt blendWindows:@YES];
 if(ct->blendingController || ct2->blendingController!=pt2 || alerts){fprintf(stderr,"FAIL: secondary command did not detach its owner without affecting unrelated pair/alerting\n");return 1;}
 [pt blendWindows:@YES];assert(ct->blendingController==pt && ct2->blendingController==pt2 && alerts==0);
 [ct blendWindows:@YES];assert(!ct->blendingController && ct2->blendingController==pt2);
 ct2->blendingController=nil;
 [ct blendWindows:@YES];assert(ct->blendingController==pt && !ct2->blendingController);
 [ct blendWindows:@YES];assert(!ct->blendingController);
 [ct blendWindows:nil];assert(ct->blendingController==pt && ct2->blendingController==pt2);
 ViewerController *mr=make(@"MR",@"C");[mr blendWindows:@YES];assert(alerts==1 && ct->blendingController==pt && ct2->blendingController==pt2);
 ct->blendingController=nil;pt->image->geometry->tilted=YES;[ct blendWindows:@YES];assert(alerts==2 && !ct->blendingController && ct2->blendingController==pt2);
 pt->image->geometry->tilted=NO;pt->gantry=YES;[ct blendWindows:@YES];assert(alerts==3 && !ct->blendingController);
 puts("PASS: CT/PT symmetric toggle, selected-pair isolation, automatic pairing and incompatible geometry diagnostics");
}}
'''.replace('COMMAND',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-fusion-command-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang',str(p/'test.m'),'-framework','Cocoa','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
