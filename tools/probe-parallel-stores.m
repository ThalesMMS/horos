// Diagnostic-only concurrent native C-STORE with per-report path attribution.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>
@interface NSObject (ParallelStoreProbe)
+ (id)activeLocalDatabase;- (NSString*)dataBaseDirPath;
- (id)initWithCallingAET:(id)a calledAET:(id)b hostname:(id)c port:(int)p filesToSend:(id)f transferSyntax:(int)t compression:(float)q extraParameters:(id)e;
- (void)run:(id)operation;- (NSInteger)sentCount;- (NSInteger)failedCount;
@end
static NSArray *senders,*reports;
static NSMutableDictionary *events,*temporaryDirectories;
static NSMutableArray *workers;
static NSString *output;
static void capture(id report,NSString *path) {
 NSUInteger i=[reports indexOfObjectIdenticalTo:report];if(i==NSNotFound)return;
 [events[[NSString stringWithFormat:@"%lu",i]] addObject:path];
}
__attribute__((constructor)) static void install(void) {
 const char *env=getenv("HOROS_STORE_PROBE");if(!env)return;
 output=[NSString stringWithUTF8String:env];if(![output containsString:@"/local-validation/"])return;
 Class cls=NSClassFromString(@"HorosStoreReport");
 Method temporary=class_getInstanceMethod(NSFileManager.class,NSSelectorFromString(@"tmpDirectoryPathInDir:"));IMP originalTemporary=method_getImplementation(temporary);
 method_setImplementation(temporary,imp_implementationWithBlock(^id(id manager,NSString *parent){
  id result=((id(*)(id,SEL,id))originalTemporary)(manager,NSSelectorFromString(@"tmpDirectoryPathInDir:"),parent);
  if([NSThread.currentThread.name hasPrefix:@"Store"] && [parent containsString:@"/local-validation/"]){@synchronized(cls){temporaryDirectories[NSThread.currentThread.name]=result;}}
  return result;
 }));
 for(NSString *name in @[@"recordSentPath:statusText:",@"recordUnreadablePath:reason:",@"recordPathWithoutIdentity:",@"recordNonStoragePath:sopClassUID:",@"recordNoPresentationContextPath:sopClassUID:transferSyntax:",@"recordRejectedPath:statusText:",@"recordTransportFailurePath:reason:"]) {
  SEL sel=NSSelectorFromString(name);Method m=class_getInstanceMethod(cls,sel);IMP original=method_getImplementation(m);unsigned count=method_getNumberOfArguments(m);
  if(count==3)method_setImplementation(m,imp_implementationWithBlock(^(id receiver,id path){@synchronized(cls){capture(receiver,path);((void(*)(id,SEL,id))original)(receiver,sel,path);}}));
  if(count==4)method_setImplementation(m,imp_implementationWithBlock(^(id receiver,id path,id a){@synchronized(cls){capture(receiver,path);((void(*)(id,SEL,id,id))original)(receiver,sel,path,a);}}));
  if(count==5)method_setImplementation(m,imp_implementationWithBlock(^(id receiver,id path,id a,id b){@synchronized(cls){capture(receiver,path);((void(*)(id,SEL,id,id,id))original)(receiver,sel,path,a,b);}}));
 }
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   id db=[NSClassFromString(@"DicomDatabase") activeLocalDatabase];if(![[db dataBaseDirPath] containsString:@"/local-validation/"])return;
   NSArray *inputs=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:[output stringByAppendingPathComponent:@"inputs.json"]] options:0 error:NULL];if(inputs.count!=2)return;
   NSMutableArray *objects=[NSMutableArray new],*reportObjects=[NSMutableArray new];events=[NSMutableDictionary new];temporaryDirectories=[NSMutableDictionary new];workers=[NSMutableArray new];
   for(NSUInteger i=0;i<2;i++) {
    int syntaxB=getenv("HOROS_STORE_SYNTAX_B")?atoi(getenv("HOROS_STORE_SYNTAX_B")):5;
    id sender=[[NSClassFromString(@"DCMTKStoreSCU") alloc] initWithCallingAET:i?@"SEND_B":@"SEND_A" calledAET:i?@"STORE_B":@"STORE_A" hostname:@"127.0.0.1" port:11320+(int)i filesToSend:inputs[i] transferSyntax:i?syntaxB:0 compression:i?1:0 extraParameters:@{@"threadStatus":@NO,@"useDCMTKForJP2K":@YES}];
    [objects addObject:sender];[reportObjects addObject:[sender valueForKey:@"report"]];events[[NSString stringWithFormat:@"%lu",i]]=[NSMutableArray new];
   }
   senders=objects;reports=reportObjects;
   for(NSUInteger i=0;i<2;i++) {
    NSThread *thread=[[NSThread alloc] initWithBlock:^{@autoreleasepool{
     if(i)[NSThread sleepForTimeInterval:.4];
     NSLog(@"PARALLEL_STORE_START %lu %.6f",i,NSProcessInfo.processInfo.systemUptime);
     @try{[senders[i] run:nil];}@catch(NSException*e){NSLog(@"PARALLEL_STORE_ERROR %lu %@",i,e.name);}
     NSLog(@"PARALLEL_STORE_END %lu %.6f sent=%ld failed=%ld",i,NSProcessInfo.processInfo.systemUptime,[reports[i] sentCount],[reports[i] failedCount]);
    }}];thread.name=[NSString stringWithFormat:@"Store%lu",i];[workers addObject:thread];[thread start];
   }
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,20*NSEC_PER_SEC),dispatch_get_main_queue(),^{
    for(NSThread*t in workers)NSLog(@"PARALLEL_STORE_WATCHDOG running=%d",t.executing);
    @synchronized(cls){[[NSJSONSerialization dataWithJSONObject:temporaryDirectories options:NSJSONWritingPrettyPrinted error:NULL] writeToFile:[output stringByAppendingPathComponent:@"temporary-directories.json"] atomically:YES];[[NSJSONSerialization dataWithJSONObject:events options:NSJSONWritingPrettyPrinted error:NULL] writeToFile:[output stringByAppendingPathComponent:@"report-paths.json"] atomically:YES];}
   });
  });
 }];
}
