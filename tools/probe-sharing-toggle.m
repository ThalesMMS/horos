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
static void later(void (^block)(void)) {dispatch_after(dispatch_time(DISPATCH_TIME_NOW,300*NSEC_PER_MSEC),dispatch_get_main_queue(),block);}
// Since #615 the listener reports ready or failed on the main queue after the toggle returns, and only a
// ready listener is advertised: the state is read once that has had time to arrive, then the next step runs.
static void change(BOOL enabled, NSString *name, void (^next)(void)) {
    double start=NSDate.timeIntervalSinceReferenceDate;
    [NSUserDefaultsController.sharedUserDefaultsController.values setValue:@(enabled) forKey:@"bonjourSharing"];
    double seconds=NSDate.timeIntervalSinceReferenceDate-start;
    later(^{
      id publisher=[NSClassFromString(@"BonjourPublisher") currentPublisher];
      NSDictionary *row=@{@"case":name,@"seconds":@(seconds),
        @"preference":@([NSUserDefaults.standardUserDefaults boolForKey:@"bonjourSharing"]),
        @"listenerPort":@([publisher OsiriXDBCurrentPort]),@"advertisedPort":@([[publisher netService] port])};
      [results addObject:row];NSLog(@"SHARING_TOGGLE %@",row);
      next();
    });
}
__attribute__((constructor)) static void install(void) {
    const char *output=getenv("HOROS_SHARING_PROBE");if(!output)return;
    NSString *path=[NSString stringWithUTF8String:output];
    if(![path containsString:@"/local-validation/"])return;
    // The sharing listener's 8780 becomes 11284: HorosDatabaseServer since #615, N2ConnectionListener before.
    Class server=NSClassFromString(@"HorosDatabaseServer");
    if(server){
        SEL selector=NSSelectorFromString(@"initWithPort:handler:");
        Method init=class_getInstanceMethod(server,selector);
        IMP original=method_getImplementation(init);
        method_setImplementation(init,imp_implementationWithBlock(^id(id receiver,uint16_t port,id handler){
            return ((id(*)(id,SEL,uint16_t,id))original)(receiver,selector,port==8780?11284:port,handler);
        }));
    }else{
        Method init=class_getInstanceMethod(NSClassFromString(@"N2ConnectionListener"),NSSelectorFromString(@"initWithPort:connectionClass:"));
        IMP original=method_getImplementation(init);
        method_setImplementation(init,imp_implementationWithBlock(^id(id receiver,NSInteger port,Class connection){
            return ((id(*)(id,SEL,NSInteger,Class))original)(receiver,NSSelectorFromString(@"initWithPort:connectionClass:"),port==8780?11284:port,connection);
        }));
    }
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
      dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        results=[NSMutableArray new];NSInteger startupPort=[[NSClassFromString(@"BonjourPublisher") currentPublisher] OsiriXDBCurrentPort];previous=[NSUserDefaults.standardUserDefaults objectForKey:@"bonjourSharing"];
        lastTick=NSDate.timeIntervalSinceReferenceDate;
        heartbeat=[NSTimer scheduledTimerWithTimeInterval:.05 repeats:YES block:^(NSTimer*t){double now=NSDate.timeIntervalSinceReferenceDate;maxGap=MAX(maxGap,now-lastTick);lastTick=now;}];
        change(NO,@"initial-off",^{
          occupied=socket(AF_INET,SOCK_STREAM,0);int yes=1;setsockopt(occupied,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
          struct sockaddr_in addr={0};addr.sin_len=sizeof(addr);addr.sin_family=AF_INET;addr.sin_port=htons(11284);addr.sin_addr.s_addr=htonl(INADDR_ANY);
          if(bind(occupied,(struct sockaddr*)&addr,sizeof(addr)) || listen(occupied,1)){NSLog(@"SHARING_PROBE_REFUSED port already occupied externally");close(occupied);occupied=-1;[heartbeat invalidate];[NSUserDefaultsController.sharedUserDefaultsController.values setValue:previous forKey:@"bonjourSharing"];return;}
          change(YES,@"occupied-on",^{change(NO,@"occupied-off",^{close(occupied);occupied=-1;
            change(YES,@"free-on",^{
              id publisher=[NSClassFromString(@"BonjourPublisher") currentPublisher];
              [publisher netService:[publisher netService] didNotPublish:@{NSNetServicesErrorCode:@(-72000),NSNetServicesErrorDomain:@(10)}];
              change(NO,@"publish-error-off",^{change(YES,@"recover-on",^{change(NO,@"final-off",^{
                [heartbeat invalidate];
                NSDictionary *report=@{@"startupListenerPort":@(startupPort),@"cases":results,@"maxHeartbeatGap":@(maxGap),@"publicationFailureInjected":@YES};
                [[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:NULL] writeToFile:[path stringByAppendingPathComponent:@"results.json"] atomically:YES];
                [NSUserDefaultsController.sharedUserDefaultsController.values setValue:previous forKey:@"bonjourSharing"];
                NSLog(@"SHARING_PROBE_DONE maxGap=%.4f",maxGap);
              });});});
            });
          });});
        });
      });
    }];
}
