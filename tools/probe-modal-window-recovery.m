// Diagnostic-only probe for #174; load only into the isolated development app.
// See docs/modal-window-recovery-validation.md. Does not query or retrieve DICOM data.
#import <Cocoa/Cocoa.h>
@interface NSObject(QueryProbe)
- (id)initAutoQuery:(BOOL)value;
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
@end
static id controller;
@interface NSObject(RecoveryProbe)
+ (id)currentBrowser;
- (void)recoverWindowsAfterScreenChange;
@end
static void record(NSString *phase, NSWindow *window) {
 NSLog(@"QUERY_FRAME %@ frame=%@ content=%@ min=%@ max=%@ screen=%@ visible=%@ scale=%.1f", phase,NSStringFromRect(window.frame),NSStringFromRect(window.contentView.bounds),NSStringFromSize(window.minSize),NSStringFromSize(window.maxSize),NSStringFromRect(window.screen.frame),NSStringFromRect(window.screen.visibleFrame),window.backingScaleFactor);
}
__attribute__((constructor)) static void install(void) {
 if(!getenv("HOROS_QUERY_WINDOW_PROBE"))return;
 if(![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"])return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
 if(![[[NSClassFromString(@"DicomDatabase") activeLocalDatabase] dataBaseDirPath] containsString:@"/local-validation/"])return;
 NSUserDefaults*d=NSUserDefaults.standardUserDefaults;NSMutableDictionary*args=[[d volatileDomainForName:NSArgumentDomain] mutableCopy];
 args[@"SERVERS"]=@[@{@"AETitle":@"SYNTH177",@"Address":@"127.0.0.1",@"Port":@11177,@"Description":@"Synthetic resize test",@"Activated":@YES,@"QR":@YES,@"Send":@YES,@"retrieveMode":@1,@"TransferSyntax":@0}];[d setVolatileDomain:args forName:NSArgumentDomain];
 controller=[[NSClassFromString(@"QueryController") alloc] initAutoQuery:NO];NSWindow*w=[controller window];
 [controller showWindow:nil];
 for(NSScreen*s in NSScreen.screens)NSLog(@"QUERY_SCREEN frame=%@ visible=%@ scale=%.1f",NSStringFromRect(s.frame),NSStringFromRect(s.visibleFrame),s.backingScaleFactor);
 for (NSNotificationName name in @[NSWindowDidResizeNotification, NSWindowDidMoveNotification, NSWindowDidEnterFullScreenNotification, NSWindowDidExitFullScreenNotification])
 [[NSNotificationCenter defaultCenter] addObserverForName:name object:w queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){record(n.name,w);}];
 record(@"initial",w);
 NSRect f=w.frame;f.origin=NSMakePoint(10000,10000);[w setFrame:f display:YES];
 record(@"query-offscreen",w);
 [NSClassFromString(@"BrowserController") currentBrowser];
 NSTimer *timer=[NSTimer timerWithTimeInterval:0.5 repeats:NO block:^(NSTimer*t){
 NSWindow *modal=NSApp.modalWindow;
 NSLog(@"RECOVERY_MODAL class=%@ present=%d",NSStringFromClass(modal.class),modal!=nil);
 NSRect r=modal.frame;r.origin=NSMakePoint(10000,10000);[modal setFrame:r display:YES];record(@"modal-offscreen",modal);
 [[NSClassFromString(@"BrowserController") currentBrowser] recoverWindowsAfterScreenChange];
 record(@"query-recovered",w);record(@"modal-recovered",modal);
 BOOL q=NO,m=NO;for(NSScreen*s in NSScreen.screens){q|=NSContainsRect(s.visibleFrame,w.frame);m|=NSContainsRect(s.visibleFrame,modal.frame);}
 NSLog(@"RECOVERY_RESULT query=%d modal=%d",q,m);
 [NSApp abortModal];
 }];
 [[NSRunLoop mainRunLoop] addTimer:timer forMode:NSModalPanelRunLoopMode];
 NSRunAlertPanel(@"Synthetic update recovery probe",@"No update request is sent.",@"Continue",nil,nil);
 NSLog(@"RECOVERY_MODAL_ENDED");
 [[[NSClassFromString(@"BrowserController") currentBrowser] window] makeKeyAndOrderFront:nil];
 [NSApp activateIgnoringOtherApps:YES];
 __block BOOL testedViewer=NO;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSWindowDidBecomeKeyNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
 NSWindow*v=n.object;
 if(testedViewer || ![v.windowController isKindOfClass:NSClassFromString(@"ViewerController")])return;
 testedViewer=YES;
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{
 NSRect r=v.frame;r.origin=NSMakePoint(10000,10000);[v setFrame:r display:YES];record(@"viewer-offscreen",v);
 [[NSClassFromString(@"BrowserController") currentBrowser] recoverWindowsAfterScreenChange];record(@"viewer-recovered",v);
 BOOL good=NO;for(NSScreen*s in NSScreen.screens)good|=NSContainsRect(s.visibleFrame,v.frame);
 NSLog(@"RECOVERY_VIEWER_RESULT visible=%d class=%@",good,NSStringFromClass(v.windowController.class));
 if(getenv("HOROS_RECOVERY_CHANGE_MODE")){
 CGDirectDisplayID display=CGMainDisplayID();CGDisplayModeRef original=CGDisplayCopyDisplayMode(display);
 NSArray *modes=CFBridgingRelease(CGDisplayCopyAllDisplayModes(display,NULL));
 __block CGDisplayModeRef target=NULL;for(id obj in modes){CGDisplayModeRef mode=(__bridge CGDisplayModeRef)obj;if(CGDisplayModeGetWidth(mode)==1440 && CGDisplayModeGetHeight(mode)==900){target=CGDisplayModeRetain(mode);break;}}
 if(target){
 __block NSTimer *finishTimer=nil;
 NSTimer*change=[NSTimer timerWithTimeInterval:0.5 repeats:NO block:^(NSTimer*t){
 NSWindow*modal=NSApp.modalWindow;
 for(NSWindow*item in @[w,v,modal]){NSRect f=item.frame;f.origin=NSMakePoint(10000,10000);[item setFrame:f display:YES];}
 NSLog(@"RECOVERY_DISPLAY_CHANGE result=%d",CGDisplaySetDisplayMode(display,target,NULL));
 finishTimer=[NSTimer timerWithTimeInterval:3 repeats:NO block:^(NSTimer*t){
 BOOL all=YES;for(NSWindow*item in @[w,v,modal]){record(@"display-notification-result",item);BOOL contained=NO;for(NSScreen*screen in NSScreen.screens)contained|=NSContainsRect(screen.visibleFrame,item.frame);all&=contained;}
 NSLog(@"RECOVERY_DISPLAY_RESULT all=%d",all);
 NSLog(@"RECOVERY_DISPLAY_RESTORE result=%d",CGDisplaySetDisplayMode(display,original,NULL));
 [NSApp abortModal];
 }];[[NSRunLoop mainRunLoop] addTimer:finishTimer forMode:NSModalPanelRunLoopMode];
 }];[[NSRunLoop mainRunLoop] addTimer:change forMode:NSModalPanelRunLoopMode];
 NSRunAlertPanel(@"Synthetic update during screen change",@"The original display mode is restored automatically.",@"Continue",nil,nil);
 [change invalidate];[finishTimer invalidate];
 CGDisplaySetDisplayMode(display,original,NULL);
 CGDisplayModeRelease(target);
 }
 CGDisplayModeRelease(original);
 }

 });
 }];


 }); }];
}
