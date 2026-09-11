#!/usr/bin/env python3
"""Execute the real modifier handler: typing Shift must not replace the field editor."""
from pathlib import Path
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
a=s.index('- (void) flagsChanged:(NSEvent *)event');method=s[a:s.index('- (void) setupToolbar',a)]
identifiers=set(re.findall(r'\b\w+ToolbarItemIdentifier\b',method))
constants='\n'.join(f'static NSString *{name}=@"{name}";' for name in sorted(identifiers))
code=r'''
#import <Cocoa/Cocoa.h>
CONSTANTS
@interface NSImage(Probe)
+ (NSImage*)toolbarImageNamed:(NSString*)name;
@end
@interface Dummy:NSObject
@property NSInteger editedRow;
@property NSUInteger modifierFlags;
- (NSArray*)items;
@end
@implementation Dummy
@synthesize editedRow,modifierFlags;
- (NSArray*)items {return @[];}
@end
@interface BrowserFixture:NSObject {
 @public id databaseOutline,toolbar; NSUInteger previousFlags; BOOL _refreshDeferredWhileEditing; NSUInteger changes;
}
- (void)outlineViewSelectionDidChange:(id)notification;
@end
@implementation BrowserFixture
- (void)outlineViewSelectionDidChange:(id)notification {changes++;}
METHOD
@end
int main(void){@autoreleasepool {
 BrowserFixture*b=[BrowserFixture new];Dummy*outline=[Dummy new],*event=[Dummy new];b->databaseOutline=outline;b->toolbar=[Dummy new];
 outline.editedRow=0;event.modifierFlags=NSEventModifierFlagShift;
 [b flagsChanged:(NSEvent*)event];
 NSCAssert(b->changes==0,@"Modifier key stole the active comment editor");
 NSCAssert(b->_refreshDeferredWhileEditing,@"Selection refresh must be deferred");
 NSCAssert(b->previousFlags==event.modifierFlags,@"Toolbar modifier state must stay current");
 outline.editedRow=-1;event.modifierFlags=0;[b flagsChanged:(NSEvent*)event];
 NSCAssert(b->changes==1,@"Normal modifier selection refresh must still run");
 [b flagsChanged:(NSEvent*)event];NSCAssert(b->changes==1,@"Unchanged modifiers must not refresh");
 NSLog(@"PASS: modifier selection refresh deferred during editing and retained outside it");
}}
'''.replace('CONSTANTS',constants).replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-comment-modifiers-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-framework','Cocoa',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
