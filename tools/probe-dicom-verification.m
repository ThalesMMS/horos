// Diagnostic-only injection. Requires a disposable local-validation database.
#import <Cocoa/Cocoa.h>
#import <stdatomic.h>
@interface NSObject (VerificationProbe)
+ (BOOL)echoServer:(NSDictionary*)server;
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
- (id)initWithDataset:(void*)dataset callingAET:(NSString*)calling calledAET:(NSString*)called hostname:(NSString*)host port:(int)port transferSyntax:(int)syntax compression:(float)compression extraParameters:(NSDictionary*)parameters;
- (void)setShowErrorMessage:(BOOL)value;
- (void)queryWithValues:(NSArray*)values;
@end
static atomic_uint ticks;
__attribute__((constructor)) static void install(void) {
 const char *input=getenv("HOROS_VERIFY_PROBE_SERVERS");
 if(!input)return;
 NSData *data=[NSData dataWithContentsOfFile:[NSString stringWithUTF8String:input]];
 NSArray *servers=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
  [NSTimer scheduledTimerWithTimeInterval:.05 repeats:YES block:^(NSTimer*t){atomic_fetch_add(&ticks,1);}];
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   id db=[NSClassFromString(@"DicomDatabase") activeLocalDatabase];
   if(![[db dataBaseDirPath] containsString:@"/local-validation/"])return;
   dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
    for(NSDictionary *server in servers){
     @autoreleasepool {
      unsigned before=atomic_load(&ticks);NSTimeInterval start=NSProcessInfo.processInfo.systemUptime;
      BOOL result=[NSClassFromString(@"OSILocationsPreferencePanePref") echoServer:server];
      NSLog(@"VERIFY_PROBE %@ result=%d seconds=%.3f ticks=%u->%u",server[@"Description"],result,NSProcessInfo.processInfo.systemUptime-start,before,atomic_load(&ticks));
      if([server[@"ProbeQuery"] boolValue]){
       id node=[[NSClassFromString(@"DCMTKRootQueryNode") alloc] initWithDataset:NULL callingAET:[[NSUserDefaults standardUserDefaults] stringForKey:@"AETITLE"] calledAET:server[@"AETitle"] hostname:server[@"Address"] port:[server[@"Port"] intValue] transferSyntax:0 compression:0 extraParameters:server];
       [node setShowErrorMessage:NO];
       [node queryWithValues:@[@{@"name":@"PatientsName",@"value":@"NOMATCH^SYNTHETIC_354"}]];
       NSLog(@"VERIFY_PROBE_QUERY %@ finished",server[@"Description"]);
      }
     }
    }
    NSLog(@"VERIFY_PROBE_DONE");
   });
  });
 }];
}
