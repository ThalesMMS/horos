// Minimal AppKit comparison for #38: a textured window and a normal window, each
// with the controls the upstream stack names (slider in a toolbar item, slider in
// the content view), exercised without Horos. Diagnostic only.
#import <Cocoa/Cocoa.h>

@interface Probe : NSObject <NSApplicationDelegate, NSToolbarDelegate>
@property NSMutableArray<NSWindow*> *windows;
@end

@implementation Probe
- (NSToolbarItem *)toolbar:(NSToolbar *)toolbar itemForItemIdentifier:(NSToolbarItemIdentifier)identifier willBeInsertedIntoToolbar:(BOOL)flag {
 NSToolbarItem *item = [[NSToolbarItem alloc] initWithItemIdentifier:identifier];
 NSView *host = [[NSView alloc] initWithFrame:NSMakeRect(0,0,140,40)];
 NSSlider *slider = [NSSlider sliderWithValue:0.5 minValue:0 maxValue:1 target:nil action:nil];
 slider.frame = NSMakeRect(0,10,140,20);
 [host addSubview:slider];
 // The same fixed-size custom view attachment ViewerController uses for WL/WW.
 item.view = host;
 item.minSize = host.frame.size;
 item.maxSize = host.frame.size;
 return item;
}
- (NSArray<NSToolbarItemIdentifier> *)toolbarAllowedItemIdentifiers:(NSToolbar *)toolbar { return @[@"WLWW"]; }
- (NSArray<NSToolbarItemIdentifier> *)toolbarDefaultItemIdentifiers:(NSToolbar *)toolbar { return @[@"WLWW"]; }

- (NSWindow *)makeWindowTextured:(BOOL)textured named:(NSString *)name {
 NSWindowStyleMask mask = NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskResizable;
 if (textured) mask |= NSWindowStyleMaskTexturedBackground;
 NSWindow *w = [[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,420,200) styleMask:mask backing:NSBackingStoreBuffered defer:NO];
 w.title = name;
 NSSlider *slider = [NSSlider sliderWithValue:0.5 minValue:0 maxValue:1 target:nil action:nil];
 slider.frame = NSMakeRect(20,40,380,20);
 [w.contentView addSubview:slider];
 NSToolbar *toolbar = [[NSToolbar alloc] initWithIdentifier:[@"probe." stringByAppendingString:name]];
 toolbar.delegate = self;
 w.toolbar = toolbar;
 [w makeKeyAndOrderFront:nil];
 return w;
}

- (void)exercise:(NSWindow *)window label:(NSString *)label {
 NSSlider *content = nil;
 for (NSView *v in ((NSView*)window.contentView).subviews) if ([v isKindOfClass:NSSlider.class]) content = (NSSlider*)v;
 NSToolbarItem *item = window.toolbar.items.firstObject;
 NSSlider *toolbarSlider = nil;
 for (NSView *v in item.view.subviews) if ([v isKindOfClass:NSSlider.class]) toolbarSlider = (NSSlider*)v;
 for (int i = 0; i <= 20; i++) {
  double value = i / 20.0;
  content.doubleValue = value; [content setNeedsDisplay:YES];
  toolbarSlider.doubleValue = 1.0 - value; [toolbarSlider setNeedsDisplay:YES];
  [window displayIfNeeded];
 }
 // Appearance changes and a resize are the reported triggers.
 for (NSAppearanceName name in @[NSAppearanceNameAqua, NSAppearanceNameDarkAqua]) {
  window.appearance = [NSAppearance appearanceNamed:name];
  [window setFrame:NSMakeRect(window.frame.origin.x, window.frame.origin.y, 520, 260) display:YES];
  [window setFrame:NSMakeRect(window.frame.origin.x, window.frame.origin.y, 420, 200) display:YES];
  [window displayIfNeeded];
 }
 NSLog(@"TEXTURED_PROBE %@ textured=%d sliders=%d/%d exercised without exception",
   label, (window.styleMask & NSWindowStyleMaskTexturedBackground) != 0, content != nil, toolbarSlider != nil);
}

- (void)applicationDidFinishLaunching:(NSNotification *)note {
 self.windows = [NSMutableArray array];
 @try {
  NSWindow *textured = [self makeWindowTextured:YES named:@"textured"];
  NSWindow *plain = [self makeWindowTextured:NO named:@"plain"];
  [self.windows addObjectsFromArray:@[textured, plain]];
  [self exercise:textured label:@"textured-window"];
  [self exercise:plain label:@"plain-window"];
  NSLog(@"TEXTURED_PROBE result=no-exception os=%@", NSProcessInfo.processInfo.operatingSystemVersionString);
 } @catch (NSException *e) {
  NSLog(@"TEXTURED_PROBE result=exception name=%@ reason=%@ stack=%@", e.name, e.reason, e.callStackSymbols);
 }
 [NSApp terminate:nil];
}
@end

int main(void) { @autoreleasepool {
 [NSApplication sharedApplication];
 Probe *probe = [Probe new];
 NSApp.delegate = probe;
 [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
 [NSApp run];
} return 0; }
