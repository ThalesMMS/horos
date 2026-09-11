#!/usr/bin/env python3
"""Exercise the production screen-change filter with controlled display snapshots."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/AppController.m']).decode('latin1') if len(sys.argv)>1 else (root/'Horos/Sources/AppController.m').read_bytes().decode('latin1'))
a=s.index('- (void)updateScreenParameters {');method=s[a:s.index('+ (void) resetThumbnailsList',a)]
code=r'''
#import <Foundation/Foundation.h>
#import <math.h>
static NSArray *snapshot;
static int closes,resets,recoveries;
#define check(c) do {if(!(c)){NSLog(@"FAIL: %s",#c);exit(1);}}while(0)
@interface NSScreen:NSObject
@property NSRect frame;
@property NSRect visibleFrame;
@property(retain) NSDictionary *deviceDescription;
+ (NSArray*)screens;
@end
@implementation NSScreen
+ (NSArray*)screens{return snapshot;}
@end
@interface BrowserController:NSObject
+ (id)currentBrowser;
- (void)recoverWindowsAfterScreenChange;
@end
@implementation BrowserController
+ (id)currentBrowser {static id browser;if(!browser)browser=[self new];return browser;}
- (void)recoverWindowsAfterScreenChange {recoveries++;}
@end
@interface AppController:NSObject
+ (id)sharedAppController;
+ (void)resetThumbnailsList;
- (void)closeAllViewers:(id)sender;
- (void)updateScreenParameters;
@end
@implementation AppController
+ (id)sharedAppController{static id app;if(!app)app=[self new];return app;}
+ (void)resetThumbnailsList{resets++;}
- (void)closeAllViewers:(id)sender{closes++;}
METHOD
@end
static NSScreen *display(int identifier,NSRect rect){NSScreen *s=[NSScreen new];s.frame=rect;s.visibleFrame=rect;s.deviceDescription=@{@"NSScreenNumber":@(identifier)};return s;}
int main(void){@autoreleasepool {
 id app=[AppController sharedAppController];
 NSScreen *a=display(1,NSMakeRect(0,0,1440,900)),*b=display(2,NSMakeRect(-1920,0,1920,1080));
 snapshot=@[a,b];[app updateScreenParameters];check(resets==1 && recoveries==1 && closes==0);
 [app updateScreenParameters];check(resets==1 && recoveries==1);
 for(int i=0;i<50;i++){snapshot=i%2?@[a,b]:@[b,a];[app updateScreenParameters];}
 check(resets==51 && recoveries==51 && closes==0);
 snapshot=@[];[app updateScreenParameters];check(resets==51 && recoveries==51 && closes==0);
 snapshot=@[a,display(2,NSZeroRect)];[app updateScreenParameters];check(resets==51 && recoveries==51 && closes==0);
 snapshot=@[a,display(2,NSMakeRect(NAN,0,1920,1080))];[app updateScreenParameters];check(resets==51 && recoveries==51 && closes==0);
 snapshot=@[a,b];[app updateScreenParameters];check(resets==51 && recoveries==51 && closes==0);
 b.frame=NSMakeRect(-1920,0,1600,900);[app updateScreenParameters];check(resets==51 && recoveries==52 && closes==0);
 b.visibleFrame=NSMakeRect(-1920,24,1600,876);[app updateScreenParameters];check(resets==51 && recoveries==53 && closes==0);
 snapshot=@[display(3,b.frame),a];[app updateScreenParameters];check(resets==52 && recoveries==54 && closes==0);
 NSLog(@"PASS: initial/duplicate/reordered/empty/invalid/geometry snapshots; real display replacement preserves viewers");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-screen-notifications-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-fblocks','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
