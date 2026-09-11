#!/usr/bin/env python3
"""A key-window change must hand the shared list to its viewer on that screen."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'Horos/Sources/ThumbnailsListPanel.m').read_bytes().decode('latin1')
start = source.index('- (void)windowDidBecomeKey:')
method = source[start:source.index('- (void)windowDidResignMain:', start)]
code = r'''
#import <Foundation/Foundation.h>
#define NSWindowAbove 1
#define check(c) do { if (!(c)) { fprintf(stderr,"FAIL: %s\n",#c); exit(1); } } while (0)
@interface NSWindow : NSObject
@property id screen;
@property id windowController;
@property BOOL isVisible;
@property int windowNumber;
- (void)makeKeyAndOrderFront:(id)sender;
- (void)orderWindow:(int)order relativeTo:(int)number;
- (void)orderOut:(id)sender;
@end
@implementation NSWindow
- (void)makeKeyAndOrderFront:(id)sender {}
- (void)orderWindow:(int)order relativeTo:(int)number { self.isVisible=YES; }
- (void)orderOut:(id)sender { self.isVisible=NO; }
@end
@interface ViewerController : NSObject
@property NSWindow *window;
@property id previewMatrixScrollView;
@end
@implementation ViewerController
@end
@interface AppController : NSObject
+ (id)thumbnailsListPanelForScreen:(id)screen;
@end
static NSDictionary *panels;
@implementation AppController
+ (id)thumbnailsListPanelForScreen:(id)screen { return panels[screen]; }
@end
@interface Panel : NSObject { @public ViewerController *viewer; }
@property NSWindow *window;
@property id list;
@property int attachments;
- (void)setThumbnailsView:(id)list viewer:(id)owner;
- (void)windowDidBecomeKey:(NSNotification *)notification;
@end
@implementation Panel
- (void)setThumbnailsView:(id)list viewer:(id)owner { self.list=list; viewer=owner; self.attachments++; }
METHOD
@end
int main(void) { @autoreleasepool {
    NSUserDefaults *defaults=NSUserDefaults.standardUserDefaults;
    [defaults setVolatileDomain:@{@"UseFloatingThumbnailsList":@YES} forName:NSArgumentDomain];
    Panel *a=[Panel new], *b=[Panel new], *spare=[Panel new]; panels=@{@0:a,@1:b};
    a.window=[NSWindow new]; b.window=[NSWindow new]; spare.window=[NSWindow new];
    ViewerController *first=[ViewerController new], *second=[ViewerController new];
    first.window=[NSWindow new]; second.window=[NSWindow new];
    first.window.windowController=first; second.window.windowController=second;
    first.window.screen=@0; second.window.screen=@1;
    first.window.isVisible=YES; second.window.isVisible=YES;
    first.previewMatrixScrollView=[NSObject new]; second.previewMatrixScrollView=[NSObject new];
    NSNotification *one=[NSNotification notificationWithName:@"key" object:first.window];
    NSNotification *two=[NSNotification notificationWithName:@"key" object:second.window];
    for (Panel *panel in @[a,b,spare]) [panel windowDidBecomeKey:one];
    check(a->viewer==first && a.list==first.previewMatrixScrollView && a.attachments==1);
    check(b.attachments==0 && spare.attachments==0);
    for (Panel *panel in @[a,b,spare]) [panel windowDidBecomeKey:two];
    check(a->viewer==first && b->viewer==second && b.attachments==1 && spare.attachments==0);
    second.window.screen=@0; [a windowDidBecomeKey:two]; // same-screen focus, no main notification
    check(a->viewer==second && a.list==second.previewMatrixScrollView && a.attachments==2);
    second.window.isVisible=NO; [a windowDidBecomeKey:two]; check(a.attachments==2);
    second.window.isVisible=YES;
    [defaults setVolatileDomain:@{@"UseFloatingThumbnailsList":@NO} forName:NSArgumentDomain];
    [a windowDidBecomeKey:two]; check(a.attachments==2);
    puts("PASS: key-only focus hands off the list; other screens, spare panels, hidden viewers and disabled mode stay untouched");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-thumbnail-key-') as folder:
    folder=Path(folder); (folder/'test.m').write_text(code)
    subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Foundation',str(folder/'test.m'),'-o',str(folder/'test')],check=True)
    subprocess.run([str(folder/'test')],check=True)
