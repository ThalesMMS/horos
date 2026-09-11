#!/usr/bin/env python3
"""Compile real selection methods with controlled AppKit window-order snapshots."""
from pathlib import Path
import subprocess, tempfile, sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/ViewerController.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/ViewerController.m').read_bytes().decode('latin1'))
a=s.index('+ (ViewerController*) frontMostDisplayed2DViewerForScreen:');b=s.index('+ (NSMutableArray*) get2DViewers',a)
methods=s[a:b].replace('static ViewerController *cachedFrontMostDisplayed2DViewer = nil;','')
code=r'''
#import <Foundation/Foundation.h>
#define check(x) do{if(!(x)){NSLog(@"FAIL: %s",#x);exit(1);}}while(0)
@interface NSScreen:NSObject @end
@implementation NSScreen @end
@interface NSWindow:NSObject
@property id windowController;
@property id screen;
@property(getter=isVisible) BOOL visible;
@end
@implementation NSWindow @end
@interface TestApp:NSObject
@property NSArray *orderedWindows;
@property NSWindow *keyWindow;
@property NSWindow *mainWindow;
@end
@implementation TestApp @end
static TestApp *NSApp;
@interface ViewerController:NSObject
@property NSWindow *window;
@property BOOL windowWillClose;
+ (ViewerController*)frontMostDisplayed2DViewerForScreen:(NSScreen*)screen;
+ (ViewerController*)frontMostDisplayed2DViewer;
+ (BOOL)isFrontMost2DViewer:(NSWindow*)window;
@end
static NSMutableDictionary *cachedFrontMostDisplayed2DViewerForScreen;
static ViewerController *cachedFrontMostDisplayed2DViewer;
@implementation ViewerController
METHODS
@end
static ViewerController *make(id screen) { ViewerController *v=[ViewerController new];v.window=[NSWindow new];v.window.screen=screen;v.window.visible=YES;v.window.windowController=v;return v; }
int main(){@autoreleasepool{
 NSApp=[TestApp new];id a=[NSScreen new],b=[NSScreen new];
 ViewerController *first=make(a),*second=make(a),*third=make(b);
 NSWindow *panel=[NSWindow new];panel.visible=YES;panel.windowController=[NSObject new];
 NSApp.orderedWindows=@[panel,first.window,second.window,third.window];
 check([ViewerController frontMostDisplayed2DViewer]==first);
 check([ViewerController frontMostDisplayed2DViewerForScreen:a]==first);
 check([ViewerController frontMostDisplayed2DViewerForScreen:b]==third);
 NSApp.mainWindow=second.window;
 check([ViewerController frontMostDisplayed2DViewer]==second);
 NSApp.keyWindow=first.window;
 check([ViewerController frontMostDisplayed2DViewer]==first);
 NSApp.keyWindow=panel;
 check([ViewerController frontMostDisplayed2DViewer]==second);
 check([ViewerController frontMostDisplayed2DViewerForScreen:b]==third);
 NSApp.keyWindow=nil;NSApp.mainWindow=nil;
 // Reordering alone need not change the application's main window.
 NSApp.orderedWindows=@[panel,second.window,first.window,third.window];
 check([ViewerController frontMostDisplayed2DViewer]==second);
 check([ViewerController frontMostDisplayed2DViewerForScreen:a]==second);
 check(![ViewerController isFrontMost2DViewer:first.window]);
 check([ViewerController isFrontMost2DViewer:second.window]);
 second.window.visible=NO;
 check([ViewerController frontMostDisplayed2DViewer]==first);
 first.windowWillClose=YES;
 check([ViewerController frontMostDisplayed2DViewer]==third);
 check([ViewerController frontMostDisplayed2DViewerForScreen:a]==nil);
 first.windowWillClose=NO;first.window.screen=b;
 check([ViewerController frontMostDisplayed2DViewerForScreen:a]==nil);
 check([ViewerController frontMostDisplayed2DViewerForScreen:b]==first);
 NSApp.orderedWindows=@[panel];
 check([ViewerController frontMostDisplayed2DViewer]==nil);
 check(![ViewerController isFrontMost2DViewer:nil]);
 NSLog(@"PASS: live ordering, auxiliary windows, visibility, closing, moved screen, empty list and nil window");
}}
'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='horos-front-viewer-') as d:
 p=Path(d);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
