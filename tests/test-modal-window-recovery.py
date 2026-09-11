#!/usr/bin/env python3
"""Exercise production recovery selection, including borderless modal panels."""
from pathlib import Path
import subprocess, tempfile, sys
root = Path(__file__).resolve().parents[1]
s = (subprocess.check_output(['git', 'show', sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('- (void)recoverWindowsAfterScreenChange\n')
method=s[a:s.index('-(void)previewMatrixScrollViewFrameDidChange:',a)]
code=r'''
#import <Foundation/Foundation.h>
#define NSWindowStyleMaskTitled 1
#define N2LogException(e) ((void)0)
@interface NSWindow:NSObject
@property NSUInteger styleMask;
@property BOOL isVisible, isMiniaturized;
@property NSRect frame;
@end
@implementation NSWindow
@end
@interface NSPanel:NSWindow
@end
@implementation NSPanel
@end
@interface App:NSObject
@property(retain) NSArray *windows;
@property(retain) NSWindow *modalWindow;
@end
@implementation App
@end
static App *NSApp;
static NSMutableArray *restored;
@interface NSScreen:NSObject
+ (NSArray*)screens;
@end
@implementation NSScreen
+ (NSArray*)screens {return @[];}
@end
@interface HorosDatabaseWindowPlacement:NSObject
+ (void)restoreWindow:(NSWindow*)w savedFrame:(NSRect)r;
@end
@implementation HorosDatabaseWindowPlacement
+ (void)restoreWindow:(NSWindow*)w savedFrame:(NSRect)r {[restored addObject:w];}
@end
@interface ToolbarPanelController:NSObject
+ (void)checkForValidToolbar;
@end
@implementation ToolbarPanelController
+ (void)checkForValidToolbar {}
@end
@interface ViewerController:NSObject
+ (id)frontMostDisplayed2DViewerForScreen:(id)s;
- (void)redrawToolbar;
@end
@implementation ViewerController
+ (id)frontMostDisplayed2DViewerForScreen:(id)s {return nil;}
- (void)redrawToolbar {}
@end
@interface Browser:NSObject
@property(retain) NSWindow *window;
- (void)recoverWindowsAfterScreenChange;
@end
@implementation Browser
METHOD
@end
#define check(c) do {if(!(c)){NSLog(@"FAIL: %s",#c);return 1;}}while(0)
int main(){@autoreleasepool{
 NSApp=[App new];restored=[NSMutableArray new];Browser*b=[Browser new];
 NSWindow *db=[NSWindow new],*viewer=[NSWindow new],*hidden=[NSWindow new],*mini=[NSWindow new],*borderless=[NSWindow new];
 NSPanel *modal=[NSPanel new],*utility=[NSPanel new];
 for(NSWindow*w in @[db,viewer,hidden,mini,utility])w.styleMask=NSWindowStyleMaskTitled;
 for(NSWindow*w in @[viewer,modal,utility,borderless])w.isVisible=YES;
 mini.isMiniaturized=YES;b.window=db;
 NSApp.windows=@[db,viewer,hidden,mini,modal,utility,borderless];NSApp.modalWindow=modal;
 [b recoverWindowsAfterScreenChange];
 check(([restored isEqualToArray:@[db,viewer,mini,modal]]));
 [restored removeAllObjects];NSApp.modalWindow=nil;[b recoverWindowsAfterScreenChange];
 check(([restored isEqualToArray:@[db,viewer,mini]]));
 NSLog(@"PASS: active borderless modal, normal/miniaturized/database windows; utility and hidden windows preserved");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-modal-recovery-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
