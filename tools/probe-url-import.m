// Diagnostic-only injection into an isolated development app. See docs/url-import-responsiveness-validation.md.
#import <Cocoa/Cocoa.h>
#import <stdatomic.h>
@interface NSObject (URLProbe)
+ (id)currentBrowser;
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
- (NSThread*)importURLs:(NSArray*)urls completion:(void (^)(NSArray*, NSString*, BOOL))completion;
@end
static atomic_uint ticks;
__attribute__((constructor)) static void setup(void) {
 const char *value = getenv("HOROS_URL_PROBE_BASE");
 if (!value) return;
 NSString *base = [NSString stringWithUTF8String:value];
 if (![[NSURL URLWithString:base].host isEqualToString:@"127.0.0.1"]) return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
  [NSTimer scheduledTimerWithTimeInterval:.05 repeats:YES block:^(NSTimer*t){atomic_fetch_add(&ticks,1);}];
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   id database = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
   if (![[database dataBaseDirPath] containsString:@"/local-validation/"]) return;
   NSLog(@"URL_PROBE_START ticks=%u",atomic_load(&ticks));
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC),dispatch_get_global_queue(0,0),^{NSLog(@"URL_PROBE_AFTER5 ticks=%u",atomic_load(&ticks));});
   BOOL cancel = getenv("HOROS_URL_PROBE_CANCEL") != NULL;
   NSArray *paths = cancel ? @[@"/never"] : @[@"/never", @"/instance", @"/slow"];
   NSMutableArray *urls = [NSMutableArray array];
   for (NSString *path in paths) [urls addObject:[NSURL URLWithString:[base stringByAppendingString:path]]];
   if (!cancel) [urls addObject:[NSURL URLWithString:@"http://127.0.0.1:1/closed"]];
   NSThread *activity = [[NSClassFromString(@"BrowserController") currentBrowser] importURLs:urls completion:^(NSArray *files, NSString *report, BOOL succeeded){
    NSLog(@"URL_PROBE_END main=%d ticks=%u files=%lu success=%d %@",NSThread.isMainThread,atomic_load(&ticks),files.count,succeeded,report);
   }];
   if (cancel) dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),dispatch_get_main_queue(),^{
    NSLog(@"URL_PROBE_CANCEL ticks=%u",atomic_load(&ticks));
    [activity cancel];
   });
  });
 }];
}
