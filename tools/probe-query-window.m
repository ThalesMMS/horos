// Diagnostic-only probe for #177; compile as a dylib and load into the isolated development app.
// See docs/query-window-sizing-validation.md. Does not query or retrieve DICOM data.
#import <Cocoa/Cocoa.h>
@interface NSObject(QueryProbe)
- (id)initAutoQuery:(BOOL)value;
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
@end
static id controller;
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
 NSRect f=w.frame;f.size=NSMakeSize(1100,850);[w setFrame:f display:YES];record(@"requested1100x850",w);
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{record(@"settled1100x850",w);[w performZoom:nil];record(@"zoom",w);});
 }); }];
}
