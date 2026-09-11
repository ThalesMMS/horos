#!/usr/bin/env python3
"""Compile the production detach/dealloc methods in MRC with real NSView ownership."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/ThumbnailsListPanel.m').read_bytes().decode('latin1')
a=s.index('- (void)prepareForScreenReconfiguration');methods=s[a:s.index('- (void)windowDidResignKey:',a)]
code=r'''
#import <AppKit/AppKit.h>
#define check(c) NSCAssert((c),@"failed: %s",#c)
static NSMutableDictionary *associatedScreen;
static int viewerDeallocs,windowHides;
@interface ViewerProbe:NSObject { @public NSView *parent; NSView *expected; }
@end
@implementation ViewerProbe
- (void)dealloc {check(expected.superview==parent);viewerDeallocs++;[parent release];[super dealloc];}
@end
@interface WindowProbe:NSObject
- (void)orderOut:(id)sender;
@end
@implementation WindowProbe
- (void)orderOut:(id)sender {windowHides++;}
@end
@interface PanelProbe:NSObject { @public NSView *thumbnailsView,*superView; ViewerProbe *viewer; }
- (BOOL)isWindowLoaded;
- (id)window;
- (void)prepareForScreenReconfiguration;
@end
@implementation PanelProbe
- (BOOL)isWindowLoaded{return YES;}
- (id)window{static id window;if(!window)window=[WindowProbe new];return window;}
METHODS
@end
static PanelProbe *attach(NSView *thumbnail) {
 PanelProbe *panel=[PanelProbe new];ViewerProbe *viewer=[ViewerProbe new];viewer->parent=[NSView new];viewer->expected=thumbnail;
 panel->viewer=viewer;panel->superView=viewer->parent;panel->thumbnailsView=[thumbnail retain];
 [associatedScreen setObject:@1 forKey:[NSValue valueWithPointer:thumbnail]];
 return panel;
}
int main(void){@autoreleasepool {
 associatedScreen=[NSMutableDictionary new];NSView *thumbnail=[NSView new],*floatingContent=[NSView new];
 [floatingContent addSubview:thumbnail];PanelProbe *panel=attach(thumbnail);
 [[NSUserDefaults standardUserDefaults] setBool:NO forKey:@"UseFloatingThumbnailsList"];
 [panel prepareForScreenReconfiguration];check(viewerDeallocs==1);check(panel->viewer==nil && panel->thumbnailsView==nil && panel->superView==nil);check(associatedScreen.count==0);
 [panel prepareForScreenReconfiguration];[panel release];check(viewerDeallocs==1);
 [floatingContent addSubview:thumbnail];panel=attach(thumbnail);[panel release];check(viewerDeallocs==2 && associatedScreen.count==0);
 panel=[PanelProbe new];[panel release];check(viewerDeallocs==2);check(windowHides==5);
 [thumbnail release];[floatingContent release];[[NSUserDefaults standardUserDefaults] removeObjectForKey:@"UseFloatingThumbnailsList"];
 NSLog(@"PASS: view returned before owner release; disabled-preference detach, idempotence, dealloc cleanup and empty panels");
}}
'''.replace('METHODS',methods)
with tempfile.TemporaryDirectory(prefix='horos-thumbnail-ownership-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-framework','AppKit',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
