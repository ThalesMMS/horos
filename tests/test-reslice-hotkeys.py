#!/usr/bin/env python3
"""Execute the real preference loading/saving and reslice dispatch with controlled focus/events."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
read = lambda p: (root / p).read_text()
header = read('Horos/Sources/DefaultsOsiriX.h')
enum = header[header.index('enum HotKeyActions'):header.index(';', header.index('enum HotKeyActions')) + 1]
pref = read('Preference Panes/OSIHotKeysPreferencePane/OSIHotKeysPref.m')
view = read('Horos/Sources/DCMView.m')
defaults = read('Horos/Sources/DefaultsOsiriX.m')


def between(text, start, end):
    a = text.index(start)
    return text[a:text.index(end, a)]


load = between(pref, '- (void) mainViewDidLoad', '\n- (NSArray *)actions')
save = between(pref, '- (NSPreferencePaneUnselectReply)shouldUnselect', '\n}') + '\n}'
assign = between(pref, '- (void) setKey:', '\n- (IBAction) specialKeyButton:')
dispatch = between(view, '                case ResliceAxialHotKeyAction:', '                case SetKeyImageAction:')
default_keys = between(defaults, '\t//hot key prefs', '\n\tNSArray *compressionSettings')

code = r'''
#import <Cocoa/Cocoa.h>
ENUM
static id storage, currentKeysPref, application;
@interface Defaults : NSObject
+(id)standardUserDefaults;
@end
@implementation Defaults
+(id)standardUserDefaults { return storage; }
@end
#define NSUserDefaults Defaults
#undef NSApp
#define NSApp application
typedef NSInteger NSPreferencePaneUnselectReply;
@interface PaneBase : NSObject
-(NSPreferencePaneUnselectReply)shouldUnselect;
@end
@implementation PaneBase
-(NSPreferencePaneUnselectReply)shouldUnselect { return 0; }
@end
@interface Pane : PaneBase {
@public NSArray *_actions; NSArrayController *arrayController;
}
-(void)setActions:(NSArray *)a;
@end
@implementation Pane
-(void)setActions:(NSArray *)a { _actions = [a retain]; }
LOAD
SAVE
ASSIGN
@end
@interface Window : NSObject
@property BOOL isKeyWindow;
@property(assign) id firstResponder;
@end
@implementation Window
@end
@interface Application : NSObject
@property(retain) NSEvent *currentEvent;
@end
@implementation Application
@end
@interface Controller : NSObject
@property NSInteger calls, requestedOrientation;
-(BOOL)setOrientation:(NSInteger)value;
@end
@implementation Controller
-(BOOL)setOrientation:(NSInteger)value { self.calls++; self.requestedOrientation=value; return YES; }
@end
@interface View : NSObject
@property BOOL is2DViewer;
@property(retain) Window *window;
@property(retain) Controller *windowController;
-(BOOL)dispatch:(int)key;
@end
@implementation View
-(BOOL)dispatch:(int)key {
    switch(key) {
DISPATCH
        default: return NO;
    }
    return YES;
}
@end
static NSEvent *event(NSEventModifierFlags flags) {
    return [NSEvent keyEventWithType:NSEventTypeKeyDown location:NSZeroPoint modifierFlags:flags
        timestamp:0 windowNumber:0 context:nil characters:@"f" charactersIgnoringModifiers:@"f"
        isARepeat:NO keyCode:3];
}
#define check(...) do { if(!(__VA_ARGS__)) { NSLog(@"FAIL %s",#__VA_ARGS__); return 1; } } while(0)
int main() { @autoreleasepool {
    storage=[NSMutableDictionary dictionary];
    // The production methods need defaults' objectForKey:/setObject:forKey: only.
    NSMutableDictionary *defaultValues=[NSMutableDictionary dictionary];
DEFAULTS
    check(SetKeyImageAction==52 && ResliceAxialHotKeyAction==53 && ResliceSagittalHotKeyAction==55);
    check(![[defaultValues objectForKey:@"HOTKEYS"] objectForKey:@""]);
    check([[[defaultValues objectForKey:@"HOTKEYS"] objectForKey:@"l"] intValue]==LengthHotKeyAction);
    [storage addEntriesFromDictionary:defaultValues];
    Pane *p=[Pane new]; [p mainViewDidLoad];
    check(p->_actions.count==56);
    for(int i=53;i<56;i++) check(![p->_actions[i] objectForKey:@"key"]);
    check([[p->_actions[53] objectForKey:@"action"] isEqual:@"Reslice Axial"]);
    p->arrayController=[[NSArrayController alloc] initWithContent:p->_actions];
    NSArray *keys=@[@"f",@"g",@"j"];
    for(int i=0;i<3;i++) { [p->arrayController setSelectionIndex:53+i]; [p setKey:keys[i]]; }
    [p shouldUnselect];
    Pane *reloaded=[Pane new]; [reloaded mainViewDidLoad];
    for(int i=0;i<3;i++) check([[reloaded->_actions[53+i] objectForKey:@"key"] isEqual:keys[i]]);
    // Existing assignments remain intact; conflicts and removal use the real pane.
    check([[[storage objectForKey:@"HOTKEYS"] objectForKey:@"l"] intValue]==LengthHotKeyAction);
    [p->arrayController setSelectionIndex:53]; [p setKey:@"l"]; [p shouldUnselect];
    check([[[storage objectForKey:@"HOTKEYS"] objectForKey:@"l"] intValue]==53);
    check([[p->_actions[LengthHotKeyAction] objectForKey:@"key"] length]==0);
    [p setKey:@""]; [p shouldUnselect]; check(![[storage objectForKey:@"HOTKEYS"] objectForKey:@"l"]);
    View *v=[View new]; v.is2DViewer=YES; v.window=[Window new];
    v.window.isKeyWindow=YES; v.window.firstResponder=v; v.windowController=[Controller new];
    application=[Application new]; [application setCurrentEvent:event(0)];
    for(int i=0;i<3;i++) { check([v dispatch:53+i]); check(v.windowController.requestedOrientation==i); }
    NSInteger calls=v.windowController.calls;
    for(NSNumber *flag in @[@(NSEventModifierFlagCommand),@(NSEventModifierFlagControl),
                            @(NSEventModifierFlagOption),@(NSEventModifierFlagShift)]) {
        [application setCurrentEvent:event(flag.unsignedIntegerValue)]; check(![v dispatch:53]);
    }
    [application setCurrentEvent:nil]; check(![v dispatch:53]);
    [application setCurrentEvent:event(0)]; v.window.firstResponder=[NSObject new]; check(![v dispatch:53]);
    v.window.firstResponder=v; v.window.isKeyWindow=NO; check(![v dispatch:53]);
    v.window.isKeyWindow=YES; v.is2DViewer=NO; check(![v dispatch:53]);
    check(v.windowController.calls==calls);
    NSLog(@"PASS: persisted IDs, default keys, pane assignment/conflict/removal/reload, three planes and focus/modifier guards");
}}
'''
for key, value in [('ENUM', enum), ('LOAD', load), ('SAVE', save), ('ASSIGN', assign),
                   ('DISPATCH', dispatch), ('DEFAULTS', default_keys)]:
    code = code.replace(key, value)
with tempfile.TemporaryDirectory(prefix='horos-reslice-hotkeys-') as folder:
    p = Path(folder)
    (p/'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', str(p/'test.m'), '-framework', 'Cocoa', '-o', str(p/'test'),
                    '-Wno-deprecated-declarations'], check=True)
    subprocess.run([str(p/'test')], check=True)
