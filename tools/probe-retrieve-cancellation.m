// Diagnostic-only: exercise a real retrieve thread in a disposable database.
#import <Cocoa/Cocoa.h>
#import <mach/mach_time.h>
@interface NSObject (RetrieveCancellationProbe)
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
- (id)initWithDataset:(void*)dataset callingAET:(NSString*)calling calledAET:(NSString*)called hostname:(NSString*)host port:(int)port transferSyntax:(int)syntax compression:(float)compression extraParameters:(NSDictionary*)parameters;
- (void)setShowErrorMessage:(BOOL)value;
- (void)setNoSmartMode:(BOOL)value;
- (void)queryWithValues:(NSArray*)values;
- (NSArray*)children;
- (void)move:(NSDictionary*)parameters retrieveMode:(int)mode;
- (NSUInteger)countOfSuboperations;
- (NSUInteger)countOfSuccessfulSuboperations;
@end
static double monotonic(void){mach_timebase_info_data_t info;mach_timebase_info(&info);return (double)mach_absolute_time()*info.numer/info.denom/1e9;}
__attribute__((constructor)) static void install(void){
 if(!getenv("HOROS_CANCEL_PROBE"))return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   id db=[NSClassFromString(@"DicomDatabase") activeLocalDatabase];
   if(![[db dataBaseDirPath] containsString:@"/local-validation/"])return;
   NSThread *thread=[[NSThread alloc] initWithBlock:^{@autoreleasepool{
    NSDictionary *server=@{@"Address":@"127.0.0.1",@"Port":@11203,@"AETitle":@"CMOVEFIX",@"TransferSyntax":@0};
    id root=[[NSClassFromString(@"DCMTKRootQueryNode") alloc] initWithDataset:NULL callingAET:@"HOROSDEV" calledAET:@"CMOVEFIX" hostname:@"127.0.0.1" port:11203 transferSyntax:0 compression:0 extraParameters:server];
    [root setShowErrorMessage:NO];
    [root queryWithValues:@[@{@"name":@"PatientsName",@"value":@"CMOVE^FIXTURE"}]];
    id study=[[root children] firstObject];
    if(!study){NSLog(@"CANCEL_PROBE_NO_STUDY");return;}
    [study setNoSmartMode:YES];[study setShowErrorMessage:NO];
    NSThread *worker=NSThread.currentThread;
    if(!getenv("HOROS_CANCEL_PROBE_COMPLETE"))dispatch_after(dispatch_time(DISPATCH_TIME_NOW,600*NSEC_PER_MSEC),dispatch_get_main_queue(),^{
      NSLog(@"CANCEL_PROBE_REQUEST time=%.6f",monotonic());[worker cancel];
    });
    NSLog(@"CANCEL_PROBE_MOVE time=%.6f",monotonic());
    [study move:@{} retrieveMode:0];
    NSLog(@"CANCEL_PROBE_END time=%.6f completed=%lu accounted=%lu cancelled=%d",monotonic(),[study countOfSuccessfulSuboperations],[study countOfSuboperations],worker.cancelled);
   }}];
   [thread start];
  });
 }];
}
