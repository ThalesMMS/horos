// Diagnostic-only C-GET batch with the real listener disabled.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>
@interface NSObject (CGETIndependentProbe)
+ (id)activeLocalDatabase;- (NSString*)dataBaseDirPath;
- (id)initWithDataset:(void*)d callingAET:(id)a calledAET:(id)b hostname:(id)c port:(int)p transferSyntax:(int)t compression:(float)f extraParameters:(id)e;
- (id)initWithCallingAET:(id)a distantServer:(id)s;
- (void)setShowErrorMessage:(BOOL)b;- (void)setNoSmartMode:(BOOL)b;
- (void)queryWithValues:(id)v;- (NSArray*)children;- (void)performRetrieve:(NSArray*)a;
- (void)retrieve:(id)sender onlyIfNotAvailable:(BOOL)only forViewing:(BOOL)view items:(NSArray*)items showGUI:(BOOL)gui;
- (void)refreshRetrieveInventory; - (id)retrieveInventory; - (id)localCompletenessForItem:(id)item;
- (NSUInteger)countOfSuccessfulSuboperations;- (NSUInteger)countOfSuboperations;
@end
static NSMutableArray *controllers, *inventoryNodes;
static IMP originalListener;

__attribute__((constructor)) static void install(void) {
 const char *config=getenv("HOROS_CGET_INDEPENDENT_PROBE");if(!config)return;
 NSString *path=[NSString stringWithUTF8String:config];if(![path containsString:@"/local-validation/"])return;
 Class listener=NSClassFromString(@"DCMTKQueryRetrieveSCP");
 Method available=class_getClassMethod(listener,NSSelectorFromString(@"storeSCP"));
 originalListener=method_getImplementation(available);
 if(getenv("HOROS_CGET_BYPASS_GUARDS")) {
  method_setImplementation(available,imp_implementationWithBlock(^BOOL(id object){return YES;}));
  Method running=class_getInstanceMethod(NSClassFromString(@"AppController"),NSSelectorFromString(@"isStoreSCPRunning"));
  method_setImplementation(running,imp_implementationWithBlock(^BOOL(id object){return YES;}));
 }
 Method notice=class_getClassMethod(NSClassFromString(@"DCMTKQueryNode"),NSSelectorFromString(@"errorMessage:"));
 method_setImplementation(notice,imp_implementationWithBlock(^(id receiver,NSArray *message){NSLog(@"CGET_NOTICE main=%d %@",NSThread.isMainThread,message);}));
 NSArray *servers=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:path] options:0 error:NULL];
 if(!servers.count)return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   if(![[[NSClassFromString(@"DicomDatabase") activeLocalDatabase] dataBaseDirPath] containsString:@"/local-validation/"])return;
   NSLog(@"CGET_REAL_LISTENER available=%d",((BOOL(*)(id,SEL))originalListener)(NSClassFromString(@"DCMTKQueryRetrieveSCP"),NSSelectorFromString(@"storeSCP")));
   controllers=[NSMutableArray new];inventoryNodes=[NSMutableArray new];NSMutableArray *workers=[NSMutableArray new];
   for(NSDictionary *server in servers) {
    id controller=[[NSClassFromString(@"QueryController") alloc] initWithWindow:nil];
    id manager=[[NSClassFromString(@"QueryArrayController") alloc] initWithCallingAET:@"HOROSDEV" distantServer:server];
    [controller setValue:manager forKey:@"queryManager"];[controllers addObject:controller];
    NSThread *worker=[[NSThread alloc] initWithBlock:^{@autoreleasepool{
     @try {
      id root=[[NSClassFromString(@"DCMTKRootQueryNode") alloc] initWithDataset:NULL callingAET:@"HOROSDEV" calledAET:server[@"AETitle"] hostname:@"127.0.0.1" port:[server[@"Port"] intValue] transferSyntax:0 compression:0 extraParameters:server];
      [root setShowErrorMessage:NO];[root queryWithValues:@[]];id study=[[root children] firstObject];
      if(!study){NSLog(@"CGET_INDEPENDENT_NO_STUDY %@",server[@"Description"]);return;}
      @synchronized(inventoryNodes){[inventoryNodes addObject:study];}
      [study setNoSmartMode:NO];[study setShowErrorMessage:YES];
      NSLog(@"CGET_INDEPENDENT_START %@ %.6f",server[@"Description"],NSProcessInfo.processInfo.systemUptime);
      if(!getenv("HOROS_INVENTORY_INSPECT_ONLY")) {
       if(getenv("HOROS_INVENTORY_USE_SELECTION")) dispatch_sync(dispatch_get_main_queue(),^{[controller retrieve:nil onlyIfNotAvailable:YES forViewing:NO items:@[study] showGUI:NO];});
       else [controller performRetrieve:@[study]];
      }
      NSLog(@"CGET_INDEPENDENT_END %@ %.6f received=%lu expected=%lu cancelled=%d",server[@"Description"],NSProcessInfo.processInfo.systemUptime,[study countOfSuccessfulSuboperations],[study countOfSuboperations],NSThread.currentThread.cancelled);
     } @catch(NSException*e){NSLog(@"CGET_INDEPENDENT_EXCEPTION %@ %@",e.name,e.reason);}
    }}];[workers addObject:worker];[worker start];
   }
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
    if(!getenv("HOROS_CGET_CANCEL"))return;
    NSLog(@"CGET_INDEPENDENT_CANCEL %.6f",NSProcessInfo.processInfo.systemUptime);
    [[workers firstObject] cancel];
   });
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,25*NSEC_PER_SEC),dispatch_get_main_queue(),^{
    for(NSThread*w in workers)NSLog(@"CGET_INDEPENDENT_WATCHDOG running=%d",w.executing);
    NSMutableArray *snapshots=[NSMutableArray new];
    for(id node in inventoryNodes) {
     [node refreshRetrieveInventory];id manifest=[node retrieveInventory];
     id cellValue=[[controllers firstObject] localCompletenessForItem:node];
     if(!manifest){NSLog(@"INVENTORY_MISSING");continue;}
     NSMutableDictionary *snapshot=[[manifest dictionaryWithValuesForKeys:@[@"inventoryConfirmed",@"expectedCount",@"importedCount",@"missingUIDs",@"duplicateUIDs",@"rejectedUIDs",@"unexpectedUIDs",@"isComplete",@"summary",@"path"]] mutableCopy];
     snapshot[@"indicator"]=[cellValue valueForKey:@"text"] ?: @"";
     snapshot[@"indicatorExplanation"]=[cellValue valueForKey:@"explanation"] ?: @"";
     [snapshots addObject:snapshot];
    }
    NSString *out=[[path stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"inventory.json"];
    [[NSJSONSerialization dataWithJSONObject:snapshots options:NSJSONWritingPrettyPrinted error:NULL] writeToFile:out atomically:YES];
    NSLog(@"INVENTORY_SNAPSHOT count=%lu",snapshots.count);
   });
  });
 }];
}
