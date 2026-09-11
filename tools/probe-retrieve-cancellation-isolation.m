// Native QueryController batches, isolated peers and diagnostic abort namespace.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>
#include <unistd.h>
#include <string.h>
static size_t fixtureConfstr(int name,char *buffer,size_t length) {
 const char *root=getenv("HOROS_ABORT_FIXTURE_ROOT");
 if(name==_CS_DARWIN_USER_TEMP_DIR && root && strstr(root,"/local-validation/")) {
  size_t needed=strlen(root)+1;if(buffer&&length){strncpy(buffer,root,length);buffer[length-1]=0;}return needed;
 }
 return confstr(name,buffer,length);
}
__attribute__((used)) static struct {const void *replacement,*original;} interpose
 __attribute__((section("__DATA,__interpose")))={(const void*)fixtureConfstr,(const void*)confstr};
@interface NSObject (IsolationProbe)
+ (id)activeLocalDatabase;- (NSString*)dataBaseDirPath;
+ (id)sharedAppController;- (void)killAllStoreSCU:(id)sender;
- (id)initWithDataset:(void*)d callingAET:(id)a calledAET:(id)b hostname:(id)c port:(int)p transferSyntax:(int)t compression:(float)f extraParameters:(id)e;
- (id)initWithCallingAET:(id)a distantServer:(id)s;
- (void)setShowErrorMessage:(BOOL)b;- (void)setNoSmartMode:(BOOL)b;
- (void)queryWithValues:(id)v;- (NSArray*)children;- (void)performRetrieve:(NSArray*)a;
- (NSUInteger)countOfSuccessfulSuboperations;- (NSUInteger)countOfSuboperations;
@end
static NSMutableArray *controllers;
__attribute__((constructor)) static void install(void) {
 const char *config=getenv("HOROS_ISOLATION_PROBE");if(!config)return;
 NSString *path=[NSString stringWithUTF8String:config];if(![path containsString:@"/local-validation/"])return;
 NSArray *servers=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:path] options:0 error:NULL];
 if(!servers.count)return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   if(![[[NSClassFromString(@"DicomDatabase") activeLocalDatabase] dataBaseDirPath] containsString:@"/local-validation/"])return;
   controllers=[NSMutableArray new];NSMutableArray *workers=[NSMutableArray new];
   for(NSDictionary *server in servers) {
    id controller=[[NSClassFromString(@"QueryController") alloc] initWithWindow:nil];
    id manager=[[NSClassFromString(@"QueryArrayController") alloc] initWithCallingAET:@"HOROSDEV" distantServer:server];
    [controller setValue:manager forKey:@"queryManager"];[controllers addObject:controller];
    NSThread *worker=[[NSThread alloc] initWithBlock:^{@autoreleasepool{
     @try {
      id root=[[NSClassFromString(@"DCMTKRootQueryNode") alloc] initWithDataset:NULL callingAET:@"HOROSDEV" calledAET:server[@"AETitle"] hostname:@"127.0.0.1" port:[server[@"Port"] intValue] transferSyntax:0 compression:0 extraParameters:server];
      [root setShowErrorMessage:NO];[root queryWithValues:@[]];id study=[[root children] firstObject];
      if(!study){NSLog(@"ISOLATION_NO_STUDY %@",server[@"Description"]);return;}
      [study setNoSmartMode:YES];[study setShowErrorMessage:NO];
      NSLog(@"ISOLATION_START %@ %.6f",server[@"Description"],NSProcessInfo.processInfo.systemUptime);
      [controller performRetrieve:@[study]];
      NSLog(@"ISOLATION_END %@ %.6f received=%lu expected=%lu cancelled=%d",server[@"Description"],NSProcessInfo.processInfo.systemUptime,[study countOfSuccessfulSuboperations],[study countOfSuboperations],NSThread.currentThread.cancelled);
     } @catch(NSException*e){NSLog(@"ISOLATION_EXCEPTION %@ %@",e.name,e.reason);}
    }}];[workers addObject:worker];[worker start];
   }
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
    if(getenv("HOROS_ISOLATION_OBSERVER"))return;
    NSLog(@"ISOLATION_CANCEL %.6f global=%d",NSProcessInfo.processInfo.systemUptime,getenv("HOROS_ISOLATION_GLOBAL")!=NULL);
    if(getenv("HOROS_ISOLATION_GLOBAL"))[[NSClassFromString(@"AppController") sharedAppController] killAllStoreSCU:nil];
    else [[workers firstObject] cancel];
   });
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,18*NSEC_PER_SEC),dispatch_get_main_queue(),^{
    for(NSThread*w in workers)NSLog(@"ISOLATION_WATCHDOG running=%d",w.executing);
   });
  });
 }];
}
