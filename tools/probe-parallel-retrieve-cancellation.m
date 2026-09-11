// Diagnostic-only parallel C-MOVE/C-GET/WADO retrieval in a private database.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>
@interface NSObject (ParallelRetrieveProbe)
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
__attribute__((constructor)) static void install(void){
 if(!getenv("HOROS_PARALLEL_CANCEL_PROBE"))return;
 if (getenv("HOROS_PROBE_CAPTURE_NOTICE")) {
  Method method = class_getClassMethod(NSClassFromString(@"DCMTKQueryNode"), @selector(errorMessage:));
  if (method) method_setImplementation(method, imp_implementationWithBlock(^(id receiver, NSArray *message){
   NSLog(@"PARALLEL_NOTICE main=%d %@", NSThread.isMainThread, message);
  }));
 }
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   id db=[NSClassFromString(@"DicomDatabase") activeLocalDatabase];
   if(![[db dataBaseDirPath] containsString:@"/local-validation/"])return;
   NSArray *servers=@[
    @{@"Description":@"C-MOVE",@"Port":@11203,@"AETitle":@"CMOVEFIX",@"retrieveMode":@0},
    @{@"Description":@"C-GET",@"Port":@(getenv("HOROS_PROBE_GET_PORT") ? atoi(getenv("HOROS_PROBE_GET_PORT")) : 11193),@"AETitle":@"CGETFIX",@"retrieveMode":@1},
    @{@"Description":@"WADO",@"Port":@11121,@"AETitle":@"WADOFIX",@"retrieveMode":@2,@"WADOUrl":@"wado",@"WADOPort":@11122}];
   NSMutableArray *workers=[NSMutableArray array];
   for(NSDictionary *entry in servers){
    NSMutableDictionary *server=[entry mutableCopy];server[@"Address"]=@"127.0.0.1";server[@"TransferSyntax"]=@0;
    NSThread *worker=[[NSThread alloc] initWithBlock:^{@autoreleasepool{
     id root=[[NSClassFromString(@"DCMTKRootQueryNode") alloc] initWithDataset:NULL callingAET:@"HOROSDEV" calledAET:server[@"AETitle"] hostname:@"127.0.0.1" port:[server[@"Port"] intValue] transferSyntax:0 compression:0 extraParameters:server];
     [root setShowErrorMessage:NO];[root queryWithValues:@[]];
     id study=[[root children] firstObject];
     if(!study){NSLog(@"PARALLEL_NO_STUDY %@",server[@"Description"]);return;}
     [study setNoSmartMode:YES];[study setShowErrorMessage:getenv("HOROS_PROBE_CAPTURE_NOTICE") != NULL];
     NSLog(@"PARALLEL_START %@ time=%.6f",server[@"Description"],NSProcessInfo.processInfo.systemUptime);
     [study move:@{@"retrieveMode":server[@"retrieveMode"]} retrieveMode:[server[@"retrieveMode"] intValue]];
     NSLog(@"PARALLEL_END %@ time=%.6f received=%lu expected=%lu report=%@",server[@"Description"],NSProcessInfo.processInfo.systemUptime,[study countOfSuccessfulSuboperations],[study countOfSuboperations],[NSThread.currentThread valueForKey:@"status"]);
    }}];
    worker.name=server[@"Description"];[workers addObject:worker];[worker start];
   }
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
    if (getenv("HOROS_PROBE_COMPLETE")) return;
    NSLog(@"PARALLEL_CANCEL time=%.6f",NSProcessInfo.processInfo.systemUptime);
    for(NSThread *worker in workers)[worker cancel];
   });
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,12*NSEC_PER_SEC),dispatch_get_main_queue(),^{
    for(NSThread *worker in workers)NSLog(@"PARALLEL_WATCHDOG %@ running=%d",worker.name,worker.executing);
   });
  });
 }];
}
