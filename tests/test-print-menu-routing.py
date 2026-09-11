#!/usr/bin/env python3
"""#384 A real AppKit menu/first-responder routing with every browser focus.

The production AppController routing/validation methods are compiled unchanged
with ARC, matching their per-file Xcode build flags; the harness remains MRC.
Pixel preparation and print panels are observers; no windows are shown.
A test NSApplication supplies the active hidden window, while AppKit itself
resolves first responders, field editing, menu validation and key equivalents. The
menu selector/target is read from every localized MainMenu.xib. --menu-source
can point at an older XIB to demonstrate the first-responder regression.
"""
import argparse
import re
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--menu-source', type=Path)
parser.add_argument('--source', type=Path, default=root/'Horos/Sources/AppController.m')
args = parser.parse_args()
source = args.source.read_bytes().decode('latin1')
pbx = (root/'Horos.xcodeproj/project.pbxproj').read_text()
build_entries = re.findall(r'/\* AppController\.m in Sources \*/ = \{[^\n]+', pbx)
assert build_entries and all('COMPILER_FLAGS = "-fobjc-arc"' in entry for entry in build_entries), 'AppController test must match the product ARC setting'
start = source.index('- (IBAction)printFromMenu:')
end = source.index('-(IBAction)showPreferencePanel:', start)
methods = source[start:end]
assert 'return [self validatePrintFromMenu:item];' in source[source.index('- (BOOL) validateMenuItem:'):]
menus = [args.menu_source] if args.menu_source else sorted((root/'Horos/Resources').glob('*.lproj/MainMenu.xib'))
routes = []
for path in menus:
    tree = ET.parse(path)
    item = tree.find('.//menuItem[@id="1550"]')
    action = item.find('./connections/action')
    target = action.attrib['target']
    if target != '-1':
        assert tree.find(f'.//customObject[@id="{target}"]').attrib['customClass'] == 'AppController', path
    routes.append((action.attrib['selector'], target, item.attrib['keyEquivalent']))
assert routes and len(set(routes)) == 1, 'localized print menus disagree'
selector, target, key = routes[0]

code = r'''
#import <AppKit/AppKit.h>
static int browserCalls, responderCalls, validationCalls;
static BOOL legacyEnabled = YES;
@interface PrintApplication : NSApplication
@property(assign) NSWindow *testKeyWindow;
@end
@implementation PrintApplication
- (NSWindow *)keyWindow { return self.testKeyWindow; }
- (NSWindow *)mainWindow { return self.testKeyWindow; }
@end
@interface BrowserController : NSWindowController
- (void)printDatabaseSelection:(id)sender;
@end
@implementation BrowserController
- (void)printDatabaseSelection:(id)sender { browserCalls++; }
@end
@interface AppController : NSObject
- (IBAction)printFromMenu:(id)sender;
- (BOOL)validatePrintFromMenu:(NSMenuItem *)item;
- (BOOL)validateMenuItem:(NSMenuItem *)item;
@end
@implementation AppController
''' + methods + r'''
- (BOOL)validateMenuItem:(NSMenuItem *)item { return [self validatePrintFromMenu:item]; }
@end
#define PRINT_OBSERVER \
- (void)print:(id)sender { responderCalls++; } \
- (BOOL)validateMenuItem:(NSMenuItem *)item { NSCAssert(item.action == @selector(print:), @"legacy validation lost selector"); validationCalls++; return legacyEnabled; }
@interface PrintMatrix : NSMatrix @end
@implementation PrintMatrix
- (BOOL)acceptsFirstResponder { return YES; }
PRINT_OBSERVER
@end
@interface PrintOutline : NSOutlineView @end
@implementation PrintOutline
PRINT_OBSERVER
@end
@interface PrintText : NSTextView @end
@implementation PrintText
PRINT_OBSERVER
@end
@interface FieldEditorProvider : NSObject <NSWindowDelegate>
@property(retain) PrintText *editor;
@end
@implementation FieldEditorProvider
- (id)windowWillReturnFieldEditor:(NSWindow *)sender toObject:(id)client { return self.editor; }
@end
static void check(BOOL passed, NSString *what) {
    if (!passed) { fprintf(stderr, "FAIL: %s (browser=%d responder=%d)\n", what.UTF8String, browserCalls, responderCalls); exit(1); }
}
static void commandP(NSMenu *menu, NSWindow *window) {
    NSEvent *event = [NSEvent keyEventWithType:NSEventTypeKeyDown location:NSZeroPoint modifierFlags:NSEventModifierFlagCommand timestamp:0 windowNumber:window.windowNumber context:nil characters:@"p" charactersIgnoringModifiers:@"p" isARepeat:NO keyCode:35];
    check([menu performKeyEquivalent:event], @"Cmd+P was not handled");
}
int main(void) { @autoreleasepool {
    [PrintApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyProhibited];
    AppController *app = [[[AppController alloc] init] autorelease];
    NSMenu *menu = [[[NSMenu alloc] initWithTitle:@"File"] autorelease];
    NSMenuItem *item = [[[NSMenuItem alloc] initWithTitle:@"Print" action:NSSelectorFromString(@"SELECTOR") keyEquivalent:@"KEY"] autorelease];
    item.target = TARGET;
    [menu addItem:item];
    NSWindow *window = [[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,320,240) styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO] autorelease];
    BrowserController *browser = [[[BrowserController alloc] initWithWindow:window] autorelease];
    [(PrintApplication *)NSApp setTestKeyWindow:window];
    check(NSApp.keyWindow == window && window.windowController == browser, @"hidden browser window must be key");
    PrintMatrix *matrix = [[[PrintMatrix alloc] initWithFrame:NSMakeRect(0,0,80,80)] autorelease];
    PrintOutline *outline = [[[PrintOutline alloc] initWithFrame:NSMakeRect(90,0,80,80)] autorelease];
    NSSearchField *search = [[[NSSearchField alloc] initWithFrame:NSMakeRect(0,120,200,22)] autorelease];
    [window.contentView addSubview:matrix]; [window.contentView addSubview:outline]; [window.contentView addSubview:search];
    FieldEditorProvider *provider = [[[FieldEditorProvider alloc] init] autorelease];
    provider.editor = [[[PrintText alloc] initWithFrame:NSZeroRect] autorelease];
    [provider.editor setFieldEditor:YES]; window.delegate = provider;
    for (NSView *view in @[matrix, outline, search]) {
        check([window makeFirstResponder:view], @"browser focus refused");
        if (view == search) {
            [search selectText:nil];
            check(window.firstResponder == provider.editor && provider.editor.isFieldEditor, @"real search field editor was not focused");
        }
        id oldTarget = [NSApp targetForAction:@selector(print:) to:nil from:item];
        check(oldTarget == window.firstResponder, @"old print: must be intercepted by focused NSView");
        browserCalls = responderCalls = 0;
        commandP(menu, window);
        check(browserCalls == 1 && responderCalls == 0, @"browser Cmd+P printed the focused control instead of selected DICOMs");
        browserCalls = responderCalls = 0;
        check([NSApp sendAction:item.action to:item.target from:item], @"menu click action refused");
        check(browserCalls == 1 && responderCalls == 0, @"browser menu click missed selection pipeline");
    }
    NSWindow *legacy = [[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,100,100) styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO] autorelease];
    NSWindowController *legacyController = [[[NSWindowController alloc] initWithWindow:legacy] autorelease];
    (void)legacyController;
    PrintText *legacyView = [[[PrintText alloc] initWithFrame:NSMakeRect(0,0,100,100)] autorelease];
    [legacy.contentView addSubview:legacyView]; [(PrintApplication *)NSApp setTestKeyWindow:legacy]; [legacy makeFirstResponder:legacyView];
    check(NSApp.keyWindow == legacy && legacy.firstResponder == legacyView, @"legacy responder setup");
    browserCalls = responderCalls = validationCalls = 0;
    commandP(menu, legacy);
    check(browserCalls == 0 && responderCalls == 1 && validationCalls > 0, @"legacy print/validation must use original responder");
    legacyEnabled = NO; [menu update];
    check(!item.enabled, @"legacy print refusal must keep menu disabled");
    puts("PASS: ARC production methods and native AppKit Cmd+P/menu click route matrix, outline and real search field editor to browser selection; other windows keep print: and validation");
    [window setDelegate:nil];
    return 0;
}}
'''
code = code.replace('SELECTOR', selector).replace('TARGET', 'nil' if target == '-1' else 'app').replace('KEY', key)
with tempfile.TemporaryDirectory(prefix='horos-print-menu-') as temporary:
    folder = Path(temporary)
    # Keep the actual production implementation in an ARC object. Test doubles
    # deliberately retain their existing manual lifecycle in the MRC driver.
    implementation_start = code.index('@implementation AppController\n')
    implementation_end = code.index('\n@end', implementation_start) + len('\n@end')
    declarations = '#import <AppKit/AppKit.h>\n' + code[code.index('@interface BrowserController'):code.index('@implementation BrowserController')] + code[code.index('@interface AppController'):implementation_start]
    (folder/'AppControllerARC.m').write_text(declarations + code[implementation_start:implementation_end])
    (folder/'Check.m').write_text(code[:implementation_start] + code[implementation_end:])
    subprocess.run(['xcrun','clang','-fobjc-arc','-c',str(folder/'AppControllerARC.m'),'-o',str(folder/'AppControllerARC.o')],check=True,timeout=30)
    subprocess.run(['xcrun','clang','-framework','AppKit',str(folder/'Check.m'),str(folder/'AppControllerARC.o'),'-o',str(folder/'check')],check=True,timeout=30)
    subprocess.run([str(folder/'check')],check=True,timeout=15)
