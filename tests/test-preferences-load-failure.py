#!/usr/bin/env python3
"""Execute the production pane-loading preflight against failing resources."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/PreferencesWindowController.mm').read_bytes().decode('latin1')
a=s.index('if (!currentContext || [currentContext.pane shouldUnselect])',s.index('-(void)setCurrentContext:'))
a=s.index('{',a)+1;b=s.index('// remove old view',a)
body=s[a:b].replace('NSAlert','ProbeAlert')
header=r'''
#import <Cocoa/Cocoa.h>
#import <PreferencePanes/PreferencePanes.h>
static int alerts;
@interface ProbeAlert:NSObject
@property(copy) NSString *messageText,*informativeText;
- (void)addButtonWithTitle:(NSString*)title;
- (void)beginSheetModalForWindow:(NSWindow*)window completionHandler:(id)handler;
@end
@implementation ProbeAlert
- (void)addButtonWithTitle:(NSString*)title {}
- (void)beginSheetModalForWindow:(NSWindow*)window completionHandler:(id)handler { alerts++; NSCAssert(self.messageText.length && self.informativeText.length,@"visible diagnosis"); }
@end
@interface TestPane:NSPreferencePane
@property int mode;
@end
@implementation TestPane
- (NSView*)loadMainView {
 if(self.mode==1)[NSException raise:@"MissingNib" format:@"fixture"];
 if(self.mode==2)return nil;
 self.mainView=[[[NSView alloc] initWithFrame:NSMakeRect(0,0,100,100)] autorelease];return self.mainView;
}
@end
@interface PreferencesWindowContext:NSObject
@property(nonatomic,retain) NSPreferencePane *pane;
@property(copy) NSString *title,*resourceName;
@property BOOL failInitializer;
@end
@implementation PreferencesWindowContext
@synthesize pane=_pane;
- (NSPreferencePane*)pane { if(self.failInitializer)[NSException raise:@"ConstructorFailure" format:@"fixture"]; return _pane; }
@end
@interface TestController:NSObject
@property(retain) NSWindow *window;
@property int commits;
- (void)select:(PreferencesWindowContext*)context;
@end
@implementation TestController
- (void)select:(PreferencesWindowContext*)context {
'''
footer=r'''
 self.commits++;
 [self didChangeValueForKey:@"currentContext"];
}
@end
int main(){ @autoreleasepool {
 TestController*c=[TestController new];
 for(int mode=1;mode<=4;mode++){
  PreferencesWindowContext*x=[PreferencesWindowContext new];x.title=@"fixture";x.resourceName=@"missing";
  TestPane*p=[[TestPane alloc] initWithBundle:NSBundle.mainBundle];p.mode=mode;x.pane=mode==4?nil:p;x.failInitializer=mode==3;
  [c select:x];NSCAssert(c.commits==0 && alerts==mode,@"failed pane must report and preserve current context");
 }
 PreferencesWindowContext*valid=[PreferencesWindowContext new];valid.pane=[[TestPane alloc] initWithBundle:NSBundle.mainBundle];
 [c select:valid];NSCAssert(c.commits==1 && alerts==4,@"valid pane switches");
 [c select:nil];NSCAssert(c.commits==2 && alerts==4,@"Show All remains available");
 puts("ok: initializer exception, missing nib, nil view and nil pane preserve prior content and report errors");
} }
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.m').write_text(header+body+footer)
 subprocess.run(['xcrun','clang','-Wno-objc-property-implementation','-framework','Cocoa','-framework','PreferencePanes',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
