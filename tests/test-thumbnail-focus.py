#!/usr/bin/env python3
"""Compile the production main-window observer with controlled screen/window peers."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/ThumbnailsListPanel.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/ThumbnailsListPanel.m').read_bytes().decode('latin1'))
a=s.index('- (void)windowDidBecomeMain:');method=s[a:s.index('- (void) thumbnailsListWillClose',a)]
code=r'''
#import <Foundation/Foundation.h>
#define NSNormalWindowLevel 0
#define NSWindowAbove 1
#define check(c) do {if(!(c)){NSLog(@"FAIL: %s",#c);exit(1);}}while(0)
static NSArray *screens;
@interface NSScreen:NSObject
+ (NSArray*)screens;
@end
@implementation NSScreen
+ (NSArray*)screens{return screens;}
@end
@interface NSWindow:NSObject
@property id screen;
@property id windowController;
@property(getter=isVisible) BOOL visible;
@property NSInteger level;
@property NSInteger windowNumber;
@property NSRect frame;
@property int activations;
- (void)makeKeyAndOrderFront:(id)sender;
- (void)orderOut:(id)sender;
- (void)orderWindow:(NSInteger)order relativeTo:(NSInteger)number;
- (void)setFrame:(NSRect)frame display:(BOOL)display;
@end
@implementation NSWindow
- (void)makeKeyAndOrderFront:(id)sender {self.activations++;self.visible=YES;}
- (void)orderOut:(id)sender {self.visible=NO;}
- (void)orderWindow:(NSInteger)order relativeTo:(NSInteger)number {self.visible=YES;}
- (void)setFrame:(NSRect)frame display:(BOOL)display {_frame=frame;}
@end
@interface ViewerController:NSObject
@property NSWindow *window;
@end
@implementation ViewerController
@end
@interface Panel:NSObject { @public ViewerController *viewer; long screen; }
@property NSWindow *window;
- (void)windowDidBecomeMain:(NSNotification*)notification;
@end
@implementation Panel
METHOD
@end
int main(void){@autoreleasepool {
 [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"UseFloatingThumbnailsList"];
 id a=[NSScreen new],b=[NSScreen new];screens=@[a,b];
 ViewerController *owner=[ViewerController new],*other=[ViewerController new];owner.window=[NSWindow new];other.window=[NSWindow new];
 owner.window.screen=a;owner.window.visible=YES;owner.window.windowNumber=1;owner.window.windowController=owner;
 other.window.screen=b;other.window.visible=YES;other.window.windowController=other;
 Panel *panel=[Panel new];panel->viewer=owner;panel->screen=0;panel.window=[NSWindow new];panel.window.visible=YES;
 NSNotification *foreign=[NSNotification notificationWithName:@"main" object:other.window];
 [panel windowDidBecomeMain:foreign];check(panel.window.visible && owner.window.activations==0);
 [panel windowDidBecomeMain:[NSNotification notificationWithName:@"main" object:owner.window]];check(panel.window.visible);
 owner.window.visible=NO;[panel windowDidBecomeMain:foreign];check(!panel.window.visible);
 owner.window.visible=YES;panel.window.visible=YES;owner.window.screen=b;[panel windowDidBecomeMain:foreign];check(!panel.window.visible);
 owner.window.screen=a;panel.window.visible=YES;other.window.level=1;[panel windowDidBecomeMain:foreign];check(panel.window.visible);other.window.level=0;
 [panel windowDidBecomeMain:[NSNotification notificationWithName:@"main" object:panel.window]];check(owner.window.activations==1);
 [[NSUserDefaults standardUserDefaults] setBool:NO forKey:@"UseFloatingThumbnailsList"];[panel windowDidBecomeMain:foreign];check(!panel.window.visible);
 [[NSUserDefaults standardUserDefaults] setBool:YES forKey:@"UseFloatingThumbnailsList"];
 screens=@[];panel.window.visible=YES;[panel windowDidBecomeMain:foreign];check(!panel.window.visible);
 screens=@[a,b];panel->screen=-1;panel.window.visible=YES;[panel windowDidBecomeMain:foreign];check(!panel.window.visible);
 [[NSUserDefaults standardUserDefaults] removeObjectForKey:@"UseFloatingThumbnailsList"];
 NSLog(@"PASS: foreign-screen focus preserved; same-screen/panel activation, hidden/moved owner, auxiliary window, disabled preference and removed screen");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-thumbnail-focus-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
