// Diagnostic-only native shared-index/authentication probe using synthetic metadata.
#import <Cocoa/Cocoa.h>
#import <CoreData/CoreData.h>
#import <objc/runtime.h>
@interface NSObject (RemoteDatabaseProbe)
+ (id)activeLocalDatabase;
+ (id)defaultDatabase;
- (NSString*)dataBaseDirPath;
- (NSString*)sqlFilePath;
- (NSString*)baseDirPath;
- (NSManagedObjectContext*)independentContext;
- (NSManagedObjectContext*)managedObjectContext;
- (id)initWithPort:(NSInteger)port connectionClass:(Class)connection;
- (void)setThreadPerConnection:(BOOL)value;
- (id)initWithHost:(NSHost*)host port:(NSInteger)port update:(BOOL)update;
- (NSString*)fetchDatabaseIndex;
- (unsigned int)fetchDatabaseIndexSize;
- (void)update;
+ (NSData*)sendSynchronousRequest:(NSData*)request toAddress:(id)address port:(NSInteger)port;
- (void)updateOnMainThread:(NSString*)path;
@end
static id listener;
static BOOL cancelPassword;
static dispatch_semaphore_t updateDone;
static NSString *probeOutput;
__attribute__((constructor)) static void install(void) {
    const char *output=getenv("HOROS_REMOTE_DB_PROBE");
    if (!output) return;
    probeOutput=[NSString stringWithUTF8String:output];
    Method method=class_getInstanceMethod(NSClassFromString(@"BrowserController"),NSSelectorFromString(@"askPassword"));
    if (!method) return;
    method_setImplementation(method,imp_implementationWithBlock(^NSString*(id browser){
        NSLog(@"REMOTE_AUTH_PROMPT main=%d",NSThread.isMainThread);
        @synchronized(NSClassFromString(@"BrowserController")) { if (cancelPassword) return nil; }
        return @"synthetic-fixture-only";
    }));
    updateDone=dispatch_semaphore_create(0);
    Method updateMethod=class_getInstanceMethod(NSClassFromString(@"RemoteDicomDatabase"),@selector(updateOnMainThread:));
    IMP originalUpdate=method_getImplementation(updateMethod);
    method_setImplementation(updateMethod,imp_implementationWithBlock(^(id remote,NSString *path){
        ((void(*)(id,SEL,id))originalUpdate)(remote,@selector(updateOnMainThread:),path);
        NSFetchRequest *request=[NSFetchRequest fetchRequestWithEntityName:@"Study"];
        NSLog(@"REMOTE_INDEX_LOADED studies=%lu asyncPathClass=%@",[[remote managedObjectContext] countForFetchRequest:request error:NULL],NSStringFromClass(path.class));
        dispatch_semaphore_signal(updateDone);
    }));
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
            id source=[NSClassFromString(@"DicomDatabase") defaultDatabase];
            if (![[source dataBaseDirPath] containsString:@"/local-validation/"]) return;
            NSMutableDictionary *arguments=[[NSUserDefaults.standardUserDefaults volatileDomainForName:NSArgumentDomain] mutableCopy];
            arguments[@"bonjourPasswordProtected"]=@(getenv("HOROS_REMOTE_DB_UNPROTECTED")==NULL);
            arguments[@"bonjourPassword"]=@"synthetic-fixture-only";
            [NSUserDefaults.standardUserDefaults setVolatileDomain:arguments forName:NSArgumentDomain];
            listener=[[NSClassFromString(@"N2ConnectionListener") alloc] initWithPort:11280 connectionClass:NSClassFromString(@"O2DatabaseConnection")];
            [listener setThreadPerConnection:YES];
            [NSThread detachNewThreadWithBlock:^{@autoreleasepool{
                @try {
                    NSManagedObjectContext *context=[source independentContext];
                    [context lock];
                    NSFetchRequest *count=[NSFetchRequest fetchRequestWithEntityName:@"Study"];
                    if ([context countForFetchRequest:count error:NULL] != 0) {
                        [context unlock]; NSLog(@"REMOTE_PROBE_REFUSED nonempty source");return;
                    }
                    NSString *padding=[@"synthetic metadata " stringByPaddingToLength:2048 withString:@"x" startingAtIndex:0];
                    for (NSUInteger i=0;i<10000;i++) {
                        NSManagedObject *study=[NSEntityDescription insertNewObjectForEntityForName:@"Study" inManagedObjectContext:context];
                        [study setValue:[NSString stringWithFormat:@"1.2.826.0.1.3680043.10.543.189.%lu",i+1] forKey:@"studyInstanceUID"];
                        [study setValue:@"SYNTHETIC^SHARED" forKey:@"name"];
                        [study setValue:[NSString stringWithFormat:@"LOCAL-SHARED-%lu",i] forKey:@"patientID"];
                        [study setValue:padding forKey:@"comment"];
                    }
                    NSError *error=nil;BOOL saved=[context save:&error];[context unlock];
                    if (!saved) {NSLog(@"REMOTE_PROBE_SAVE_FAILED %@",error);return;}
                    NSString *sourcePath=[source sqlFilePath];
                    NSLog(@"REMOTE_SOURCE_READY studies=10000 bytes=%llu",[[NSFileManager.defaultManager attributesOfItemAtPath:sourcePath error:NULL] fileSize]);
                    if (getenv("HOROS_REMOTE_DB_AUTHORIZATION_PROBE")) {
                        NSData *unauthenticated=[NSClassFromString(@"N2Connection") sendSynchronousRequest:[NSData dataWithBytes:"DATAB" length:6] toAddress:@"127.0.0.1" port:11280];
                        NSLog(@"REMOTE_UNAUTHENTICATED_INDEX_BYTES %lu",unauthenticated.length);
                    }
                    id remote=[[NSClassFromString(@"RemoteDicomDatabase") alloc] initWithHost:[NSHost hostWithAddress:@"127.0.0.1"] port:11280 update:NO];
                    NSLog(@"REMOTE_LAZY_AUTH_SIZE bytes=%u",[remote fetchDatabaseIndexSize]);
                    NSString *index=[remote fetchDatabaseIndex];
                    NSString *snapshot=[probeOutput stringByAppendingPathComponent:@"received.sql"];
                    [NSFileManager.defaultManager copyItemAtPath:index toPath:snapshot error:NULL];
                    NSLog(@"REMOTE_INDEX_RECEIVED bytes=%llu pathClass=%@",[[NSFileManager.defaultManager attributesOfItemAtPath:index error:NULL] fileSize],NSStringFromClass(index.class));
                    @autoreleasepool { [remote update]; }
                    if(dispatch_semaphore_wait(updateDone,dispatch_time(DISPATCH_TIME_NOW,10*NSEC_PER_SEC))!=0) {
                        NSLog(@"REMOTE_PROBE_EXCEPTION asynchronous update timed out");return;
                    }
                    if (getenv("HOROS_REMOTE_DB_UNPROTECTED")) {
                        dispatch_async(dispatch_get_main_queue(),^{NSLog(@"REMOTE_UNPROTECTED_READY");});return;
                    }
                    if (getenv("HOROS_REMOTE_DB_LEGACY")) {
                        id legacy=[[NSClassFromString(@"RemoteDicomDatabase") alloc] initWithHost:[NSHost hostWithAddress:@"127.0.0.1"] port:11283 update:NO];
                        @try {[legacy fetchDatabaseIndex];NSLog(@"REMOTE_LEGACY_PROTECTED_ACCEPTED");}
                        @catch(NSException *e){NSLog(@"REMOTE_LEGACY_PROTECTED_REJECTED %@",e.name);}
                    }
                    [remote setValue:@"incorrect-synthetic-answer" forKey:@"password"];
                    @try {[remote fetchDatabaseIndex];NSLog(@"REMOTE_WRONG_PASSWORD_ACCEPTED");}
                    @catch(NSException *e){NSLog(@"REMOTE_WRONG_PASSWORD_REJECTED %@",e.name);}
                    @synchronized(NSClassFromString(@"BrowserController")) {cancelPassword=YES;}
                    NSString *cancelled=[remote fetchDatabaseIndex];
                    NSLog(@"REMOTE_PASSWORD_CANCELLED result=%d",cancelled==nil);
                    @synchronized(NSClassFromString(@"BrowserController")) {cancelPassword=NO;}
                    id unavailable=[[NSClassFromString(@"RemoteDicomDatabase") alloc] initWithHost:[NSHost hostWithAddress:@"127.0.0.1"] port:11281 update:NO];
                    @try {[unavailable fetchDatabaseIndex];NSLog(@"REMOTE_NETWORK_FAILURE_ACCEPTED");}
                    @catch(NSException *e){NSLog(@"REMOTE_NETWORK_FAILURE_CAUGHT %@",e.name);}
                    if (getenv("HOROS_REMOTE_DB_TRUNCATE")) {
                        id truncated=[[NSClassFromString(@"RemoteDicomDatabase") alloc] initWithHost:[NSHost hostWithAddress:@"127.0.0.1"] port:11282 update:NO];
                        @try {
                            NSString *partial=[truncated fetchDatabaseIndex];
                            if (getenv("HOROS_REMOTE_DB_RETRY")) {
                                [NSFileManager.defaultManager copyItemAtPath:partial toPath:[probeOutput stringByAppendingPathComponent:@"retry.sql"] error:NULL];
                                NSLog(@"REMOTE_RETRY_INDEX_RECEIVED bytes=%llu",[[NSFileManager.defaultManager attributesOfItemAtPath:partial error:NULL] fileSize]);
                            } else NSLog(@"REMOTE_TRUNCATION_ACCEPTED bytes=%llu",[[NSFileManager.defaultManager attributesOfItemAtPath:partial error:NULL] fileSize]);
                        } @catch(NSException *e){
                            NSArray *files=[NSFileManager.defaultManager contentsOfDirectoryAtPath:[truncated baseDirPath] error:NULL];
                            NSUInteger partials=0;for(NSString *file in files)if([file hasPrefix:@"file-"])partials++;
                            NSLog(@"REMOTE_TRUNCATION_REJECTED %@ partials=%lu",e.name,partials);
                        }
                    }
                    dispatch_async(dispatch_get_main_queue(),^{NSLog(@"REMOTE_PROBE_MAIN_ALIVE");if(!getenv("HOROS_REMOTE_DB_HOLD_SERVER"))listener=nil;});
                } @catch(NSException *e){NSLog(@"REMOTE_PROBE_EXCEPTION %@ %@",e.name,e.reason);}
            }}];
        });
    }];
}
