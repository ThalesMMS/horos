// Private diagnostic probe: real preference observer/listener, synthetic publish error.
#import <Cocoa/Cocoa.h>
#import <sys/socket.h>
#import <netinet/in.h>
#import <unistd.h>
#import <objc/runtime.h>
@interface NSObject (SharingProbe)
+ (id)currentPublisher;
- (int)OsiriXDBCurrentPort;
- (NSNetService*)netService;
- (void)netService:(NSNetService*)service didNotPublish:(NSDictionary*)error;
@end
static NSMutableArray *results;
static id previous;
static NSTimer *heartbeat;
static double lastTick, maxGap;
static int occupied=-1;
static void change(BOOL enabled, NSString *name) {
    double start=NSDate.timeIntervalSinceReferenceDate;
    [NSUserDefaultsController.sharedUserDefaultsController.values setValue:@(enabled) forKey:@"bonjourSharing"];
    id publisher=[NSClassFromString(@"BonjourPublisher") currentPublisher];
    NSDictionary *row=@{@"case":name,@"seconds":@(NSDate.timeIntervalSinceReferenceDate-start),
      @"preference":@([NSUserDefaults.standardUserDefaults boolForKey:@"bonjourSharing"]),
      @"listenerPort":@([publisher OsiriXDBCurrentPort]),@"advertisedPort":@([[publisher netService] port])};
    [results addObject:row];NSLog(@"SHARING_TOGGLE %@",row);
}
static void later(void (^block)(void)) {dispatch_after(dispatch_time(DISPATCH_TIME_NOW,300*NSEC_PER_MSEC),dispatch_get_main_queue(),block);}
__attribute__((constructor)) static void install(void) {
    const char *output=getenv("HOROS_SHARING_PROBE");if(!output)return;
    NSString *path=[NSString stringWithUTF8String:output];
    if(![path containsString:@"/local-validation/"])return;
    Method init=class_getInstanceMethod(NSClassFromString(@"N2ConnectionListener"),NSSelectorFromString(@"initWithPort:connectionClass:"));
    IMP original=method_getImplementation(init);
    method_setImplementation(init,imp_implementationWithBlock(^id(id receiver,NSInteger port,Class connection){
        return ((id(*)(id,SEL,NSInteger,Class))original)(receiver,NSSelectorFromString(@"initWithPort:connectionClass:"),port==8780?11284:port,connection);
    }));
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
      dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        results=[NSMutableArray new];NSInteger startupPort=[[NSClassFromString(@"BonjourPublisher") currentPublisher] OsiriXDBCurrentPort];previous=[NSUserDefaults.standardUserDefaults objectForKey:@"bonjourSharing"];
        lastTick=NSDate.timeIntervalSinceReferenceDate;
        heartbeat=[NSTimer scheduledTimerWithTimeInterval:.05 repeats:YES block:^(NSTimer*t){double now=NSDate.timeIntervalSinceReferenceDate;maxGap=MAX(maxGap,now-lastTick);lastTick=now;}];
        change(NO,@"initial-off");
        occupied=socket(AF_INET,SOCK_STREAM,0);int yes=1;setsockopt(occupied,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
        struct sockaddr_in addr={0};addr.sin_len=sizeof(addr);addr.sin_family=AF_INET;addr.sin_port=htons(11284);addr.sin_addr.s_addr=htonl(INADDR_ANY);
        if(bind(occupied,(struct sockaddr*)&addr,sizeof(addr)) || listen(occupied,1)){NSLog(@"SHARING_PROBE_REFUSED port already occupied externally");close(occupied);occupied=-1;[heartbeat invalidate];[NSUserDefaultsController.sharedUserDefaultsController.values setValue:previous forKey:@"bonjourSharing"];return;}
        change(YES,@"occupied-on");later(^{change(NO,@"occupied-off");close(occupied);occupied=-1;
          later(^{change(YES,@"free-on");later(^{
            id publisher=[NSClassFromString(@"BonjourPublisher") currentPublisher];
            [publisher netService:[publisher netService] didNotPublish:@{NSNetServicesErrorCode:@(-72000),NSNetServicesErrorDomain:@(10)}];
            change(NO,@"publish-error-off");later(^{change(YES,@"recover-on");later(^{change(NO,@"final-off");
              [heartbeat invalidate];
              NSDictionary *report=@{@"startupListenerPort":@(startupPort),@"cases":results,@"maxHeartbeatGap":@(maxGap),@"publicationFailureInjected":@YES};
              [[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:NULL] writeToFile:[path stringByAppendingPathComponent:@"results.json"] atomically:YES];
              [NSUserDefaultsController.sharedUserDefaultsController.values setValue:previous forKey:@"bonjourSharing"];
              NSLog(@"SHARING_PROBE_DONE maxGap=%.4f",maxGap);
            });});
          });});
        });
      });
    }];
}
