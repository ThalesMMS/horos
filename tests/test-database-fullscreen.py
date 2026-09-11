#!/usr/bin/env python3
"""Verify production fullscreen forwarding and preservation of the windowed frame."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
a=s.index('- (IBAction)fullScreenMenu:');methods=s[a:s.index('- (void)showDatabase:',a)]
a=s.index('    NSRect savedFrame = self.window.frame;');b=s.index('\n',s.index('forKey:@"DBWindowFrame"]',a));save=s[a:b]
code=r'''
#import <AppKit/AppKit.h>
#define check(c) NSCAssert((c),@"failed: %s",#c)
@interface WindowProbe:NSObject
@property NSRect frame;
@property NSWindowStyleMask styleMask;
@property id sender;
- (void)toggleFullScreen:(id)sender;
@end
@implementation WindowProbe
- (void)toggleFullScreen:(id)sender{self.sender=sender;}
@end
@interface BrowserProbe:NSObject { NSRect _databaseWindowedFrame; }
@property WindowProbe *window;
- (void)saveFrame;
@end
@implementation BrowserProbe
METHODS
- (void)saveFrame { SAVE }
@end
int main(void){@autoreleasepool {
 BrowserProbe *browser=[BrowserProbe new];browser.window=[WindowProbe new];NSRect original=NSMakeRect(-1000,40,900,700);browser.window.frame=original;
 id sender=[NSObject new];[browser fullScreenMenu:sender];check(browser.window.sender==sender);
 [browser windowWillEnterFullScreen:[NSNotification notificationWithName:@"enter" object:browser.window]];
 browser.window.frame=NSMakeRect(0,0,1700,1100);browser.window.styleMask=NSWindowStyleMaskFullScreen;
 [browser windowWillEnterFullScreen:[NSNotification notificationWithName:@"other" object:[WindowProbe new]]];
 [browser saveFrame];check(NSEqualRects(NSRectFromString([NSUserDefaults.standardUserDefaults stringForKey:@"DBWindowFrame"]),original));
 browser.window.styleMask=0;browser.window.frame=NSMakeRect(20,40,800,600);[browser saveFrame];check(NSEqualRects(NSRectFromString([NSUserDefaults.standardUserDefaults stringForKey:@"DBWindowFrame"]),browser.window.frame));
 [NSUserDefaults.standardUserDefaults removeObjectForKey:@"DBWindowFrame"];
 NSLog(@"PASS: native toggle forwarding, own-window notification, normal geometry saved while fullscreen and updated after exit");
}}
'''.replace('METHODS',methods).replace('SAVE',save)
with tempfile.TemporaryDirectory(prefix='horos-database-fullscreen-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fobjc-arc','-framework','AppKit',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
