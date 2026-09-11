#!/usr/bin/env python3
"""Exercise the actual toolbar redraw across independent screen/panel fixtures."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/ViewerController.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/ViewerController.m').read_bytes().decode('latin1'))
a=s.index('- (void) redrawToolbar\n');method=s[a:s.index('- (void) refreshToolbar',a)]
code=r'''
#import <Foundation/Foundation.h>
#define MAXSCREENS 2
static NSArray *screens;
static int screenUpdateDepth;
static void NSDisableScreenUpdates(void){screenUpdateDepth++;}
static void NSEnableScreenUpdates(void){screenUpdateDepth--;}
#define N2LogStackTrace(x) NSLog(@"%@",x)
#define check(c) do {if(!(c)){NSLog(@"FAIL: %s",#c);exit(1);}}while(0)
@interface NSScreen:NSObject
+ (NSArray*)screens;
@end
@implementation NSScreen
+ (NSArray*)screens{return screens;}
@end
@interface Window:NSObject
@property id screen;
@property BOOL visible;
@property id toolbar;
@property BOOL customizationPaletteIsRunning;
- (void)orderOut:(id)sender;
- (void)orderBack:(id)sender;
- (void)orderFront:(id)sender;
@end
@implementation Window
- (void)orderOut:(id)sender{self.visible=NO;}
- (void)orderBack:(id)sender{self.visible=YES;}
- (void)orderFront:(id)sender{self.visible=YES;}
@end
@interface Panel:NSObject
@property id thumbnailsView;
@property id viewer;
@property Window *window;
@property BOOL fail;
- (void)setThumbnailsView:(id)view viewer:(id)viewer;
@end
@implementation Panel
- (id)init{if((self=[super init]))self.window=[Window new];return self;}
- (void)setThumbnailsView:(id)view viewer:(id)viewer {if(self.fail)[NSException raise:@"fixture" format:@"panel failure"];self.thumbnailsView=view;self.viewer=viewer;self.window.visible=view!=nil;}
@end
static Panel *thumbnailsListPanel[MAXSCREENS];
@interface AppController:NSObject
+ (BOOL)USETOOLBARPANEL;
@end
@implementation AppController
+ (BOOL)USETOOLBARPANEL{return NO;}
@end
@interface ViewerController:NSObject { @public id previewMatrixScrollView; Panel *toolbarPanel; BOOL FullScreenOn; }
@property Window *window;
+ (BOOL)isFrontMost2DViewer:(id)window;
- (void)redrawToolbar;
@end
@implementation ViewerController
+ (BOOL)isFrontMost2DViewer:(id)window{return YES;}
METHOD
@end
int main(void){@autoreleasepool {
 [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"UseFloatingThumbnailsList"];
 [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"SeriesListVisible"];
 id first=[NSScreen new],second=[NSScreen new];screens=@[first,second];
 ViewerController *a=[ViewerController new],*b=[ViewerController new];a.window=[Window new];b.window=[Window new];a.window.screen=first;b.window.screen=second;
 a->previewMatrixScrollView=[NSObject new];b->previewMatrixScrollView=[NSObject new];
 for(int i=0;i<MAXSCREENS;i++)thumbnailsListPanel[i]=[Panel new];
 [a redrawToolbar];[b redrawToolbar];
 check(thumbnailsListPanel[0].window.visible && thumbnailsListPanel[1].window.visible);
 check(thumbnailsListPanel[0].viewer==a && thumbnailsListPanel[1].viewer==b);
 [a redrawToolbar];check(thumbnailsListPanel[1].window.visible);check(screenUpdateDepth==0);
 // Move A to B's display: release A's stale panel, attach A to its new screen.
 a.window.screen=second;[a redrawToolbar];check(thumbnailsListPanel[0].viewer==nil);check(thumbnailsListPanel[1].viewer==a);
 screens=@[first,second,[NSScreen new]];[a redrawToolbar];check(screenUpdateDepth==0);
 thumbnailsListPanel[1].fail=YES;@try{[a redrawToolbar];check(NO);}@catch(NSException *e){}check(screenUpdateDepth==0);thumbnailsListPanel[1].fail=NO;
 [[NSUserDefaults standardUserDefaults] setBool:NO forKey:@"SeriesListVisible"];
 [b redrawToolbar];check(!thumbnailsListPanel[0].window.visible && !thumbnailsListPanel[1].window.visible);
 [[NSUserDefaults standardUserDefaults] removeObjectForKey:@"UseFloatingThumbnailsList"];
 [[NSUserDefaults standardUserDefaults] removeObjectForKey:@"SeriesListVisible"];
 NSLog(@"PASS: independent visible panels, owner reassignment, capacity bound, exception-safe display updates and global hide preference");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-thumbnail-screens-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
