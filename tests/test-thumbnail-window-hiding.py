#!/usr/bin/env python3
"""The real window override must not reattach a list during detach or on a spare panel."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'Horos/Sources/ThumbnailsListNSWindow.m').read_bytes().decode('latin1')
start = source.index('- (void)hideForReconfiguration')
methods = source[start:source.index('-(NSTimeInterval)animationResizeTime:', start)]
code = r'''
#import <Foundation/Foundation.h>
#define check(c) do { if (!(c)) { fprintf(stderr,"FAIL: %s\n",#c); exit(1); } } while (0)
#define NSWindowBelow -1
static int hides, orders, attachments, updateDepth;
void NSDisableScreenUpdates(void) { updateDepth++; }
void NSEnableScreenUpdates(void) { updateDepth--; }
@interface WindowBase : NSObject
@property id screen;
@property id windowController;
@property int windowNumber;
- (void)orderOut:(id)sender;
- (void)orderWindow:(int)order relativeTo:(int)number;
@end
@implementation WindowBase
- (void)orderOut:(id)sender { hides++; }
- (void)orderWindow:(int)order relativeTo:(int)number { orders++; }
@end
@interface Panel : NSObject
@property WindowBase *window;
- (void)setThumbnailsView:(id)view viewer:(id)viewer;
@end
@implementation Panel
- (void)setThumbnailsView:(id)view viewer:(id)viewer { attachments++; }
@end
@interface ViewerController : NSObject
@property WindowBase *window;
@property id previewMatrixScrollView;
+ (id)frontMostDisplayed2DViewerForScreen:(id)screen;
@end
static ViewerController *front;
@implementation ViewerController
+ (id)frontMostDisplayed2DViewerForScreen:(id)screen { return front; }
@end
@interface AppController : NSObject
+ (Panel *)thumbnailsListPanelForScreen:(id)screen;
@end
static Panel *registered;
@implementation AppController
+ (Panel *)thumbnailsListPanelForScreen:(id)screen { return registered; }
@end
@interface ThumbnailsListNSWindow : WindowBase
- (void)hideForReconfiguration;
@end
@implementation ThumbnailsListNSWindow
METHODS
@end
int main(void) { @autoreleasepool {
    NSUserDefaults *defaults=NSUserDefaults.standardUserDefaults;
    [defaults setVolatileDomain:@{@"SeriesListVisible":@YES,@"UseFloatingThumbnailsList":@YES} forName:NSArgumentDomain];
    ThumbnailsListNSWindow *window=[ThumbnailsListNSWindow new];
    registered=[Panel new]; registered.window=window; window.windowController=registered;
    front=[ViewerController new]; front.window=[WindowBase new]; front.window.windowNumber=2;
    front.previewMatrixScrollView=[NSObject new];
    [window hideForReconfiguration];
    check(hides==1 && attachments==0 && orders==0 && updateDepth==0);
    [window orderOut:nil];
    check(hides==1 && attachments==1 && orders==1 && updateDepth==0); // ordinary fallback preserved
    ThumbnailsListNSWindow *spare=[ThumbnailsListNSWindow new];
    spare.screen=window.screen; spare.windowController=[Panel new];
    [spare orderOut:nil];
    check(hides==2 && attachments==1 && orders==1 && updateDepth==0);
    registered=nil; [window orderOut:nil]; // screen removed or mapping replaced
    check(hides==3 && attachments==1);
    registered=[Panel new]; registered.window=window;
    [defaults setVolatileDomain:@{@"SeriesListVisible":@YES,@"UseFloatingThumbnailsList":@NO} forName:NSArgumentDomain];
    [window orderOut:nil]; check(hides==4 && attachments==1);
    [defaults setVolatileDomain:@{@"SeriesListVisible":@NO,@"UseFloatingThumbnailsList":@YES} forName:NSArgumentDomain];
    [window orderOut:nil]; check(hides==5 && attachments==1);
    puts("PASS: explicit detach cannot reattach; spare/unmapped panels remain hidden; ordinary owner fallback and disabled preferences preserved");
}}
'''.replace('METHODS', methods)
with tempfile.TemporaryDirectory(prefix='horos-thumbnail-hide-') as folder:
    folder=Path(folder); (folder/'test.m').write_text(code)
    subprocess.run(['xcrun','clang','-fobjc-arc','-framework','Foundation',str(folder/'test.m'),'-o',str(folder/'test')],check=True)
    subprocess.run([str(folder/'test')],check=True)
