// Diagnostic-only probe for #177; compile as a dylib and load into the isolated development app.
// See docs/query-window-sizing-validation.md. Does not query or retrieve DICOM data.
#import <Cocoa/Cocoa.h>
@interface NSObject(QueryFullScreenProbe)
- (id)initAutoQuery:(BOOL)value;
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
@end
static id controller;
static NSRect windowed;
static void record(NSString *phase, NSWindow *window) {
 NSLog(@"QUERY_FS %@ frame=%@ content=%@ min=%@ level=%ld fullScreen=%d primary=%d visible=%@",
  phase, NSStringFromRect(window.frame), NSStringFromRect(window.contentView.bounds),
  NSStringFromSize(window.minSize), (long)window.level,
  (window.styleMask & NSWindowStyleMaskFullScreen) != 0,
  (window.collectionBehavior & NSWindowCollectionBehaviorFullScreenPrimary) != 0,
  NSStringFromRect(window.screen.visibleFrame));
}
// Report the controls a user needs, with the rectangle each one occupies in the
// content view, so "accessible" is measured and not asserted.
static void reportControls(NSWindow *window) {
 NSRect content = window.contentView.bounds;
 __block __weak void (^weakWalk)(NSView *);
 void (^walk)(NSView *) = ^(NSView *view) {
  for (NSView *child in view.subviews) {
   NSString *label = nil;
   if ([child isKindOfClass:NSButton.class]) label = [(NSButton*)child title];
   else if ([child isKindOfClass:NSSearchField.class]) label = @"<search field>";
   else if ([child isKindOfClass:NSOutlineView.class]) label = @"<outline view>";
   else if ([child isKindOfClass:NSTableView.class]) label = @"<table view>";
   if (label.length && !child.isHiddenOrHasHiddenAncestor) {
    NSRect r = [child convertRect:child.bounds toView:window.contentView];
    NSLog(@"QUERY_FS_CONTROL name=%@ rect=%@ inside=%d", label, NSStringFromRect(r), NSContainsRect(content, r));
   }
   weakWalk(child);
  }
 };
 weakWalk = walk;
 walk(window.contentView);
}
__attribute__((constructor)) static void install(void) {
 if(!getenv("HOROS_QUERY_FULLSCREEN_PROBE"))return;
 if(![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"])return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
 if(![[[NSClassFromString(@"DicomDatabase") activeLocalDatabase] dataBaseDirPath] containsString:@"/local-validation/"])return;
 NSUserDefaults*d=NSUserDefaults.standardUserDefaults;NSMutableDictionary*args=[[d volatileDomainForName:NSArgumentDomain] mutableCopy];
 args[@"SERVERS"]=@[@{@"AETitle":@"SYNTH177",@"Address":@"127.0.0.1",@"Port":@11177,@"Description":@"Synthetic resize test",@"Activated":@YES,@"QR":@YES,@"Send":@YES,@"retrieveMode":@1,@"TransferSyntax":@0}];
 // Keep on Top is the case that used to leave a floating window over the menu bar.
 args[@"KeepQRWindowOnTop"]=@YES;
 [d setVolatileDomain:args forName:NSArgumentDomain];
 controller=[[NSClassFromString(@"QueryController") alloc] initAutoQuery:NO];NSWindow*w=[controller window];
 [controller showWindow:nil];[w makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
 windowed=w.frame;
 record(@"windowed",w);reportControls(w);
 [[NSNotificationCenter defaultCenter] addObserverForName:NSWindowDidEnterFullScreenNotification object:w queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*e){
  record(@"entered",w);reportControls(w);
  NSLog(@"QUERY_FS_CHECK coversVisible=%d", NSContainsRect(w.frame, w.screen.visibleFrame));
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   // Exercise the same responder-chain command again to leave full screen.
   NSLog(@"QUERY_FS_SEND leave=%d",[NSApp sendAction:@selector(fullScreenMenu:) to:nil from:nil]);
  });
 }];
 [[NSNotificationCenter defaultCenter] addObserverForName:NSWindowDidExitFullScreenNotification object:w queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*e){
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{
   record(@"exited",w);reportControls(w);
   NSLog(@"QUERY_FS_CHECK restored=%d level=%ld",NSEqualRects(w.frame,windowed),(long)w.level);
   // Zoom after the round trip must stay inside the visible rectangle.
   [w performZoom:nil];
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{
    record(@"zoomed",w);
    NSLog(@"QUERY_FS_CHECK zoomInsideVisible=%d",NSContainsRect(NSInsetRect(w.screen.visibleFrame,-1,-1),w.frame));
    NSLog(@"QUERY_FS_DONE");
   });
  });
 }];
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{
  // The Format - Fullscreen menu item targets the first responder; this is the same dispatch.
  NSLog(@"QUERY_FS_SEND enter=%d",[NSApp sendAction:@selector(fullScreenMenu:) to:nil from:nil]);
 });
 }); }];
}
