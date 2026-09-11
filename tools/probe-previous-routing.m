// Diagnostic-only entry into the native autorouting path with a private database.
#import <Cocoa/Cocoa.h>
@interface NSObject (PreviousRoutingProbe)
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
- (id)studyEntity;
- (NSArray*)objectsForEntity:(id)e predicate:(id)p;
- (void)applyRoutingRules:(id)rules toImages:(id)images;
@end
__attribute__((constructor)) static void install(void) {
 const char *env=getenv("HOROS_PREVIOUS_ROUTING_PROBE");if(!env)return;
 NSString *directory=[NSString stringWithUTF8String:env];if(![directory containsString:@"/local-validation/"])return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,12*NSEC_PER_SEC),dispatch_get_main_queue(),^{
   id db=[NSClassFromString(@"DicomDatabase") activeLocalDatabase];if(![[db dataBaseDirPath] containsString:@"/local-validation/"])return;
   NSArray *studies=[db objectsForEntity:[db studyEntity] predicate:[NSPredicate predicateWithFormat:@"id == %@",@"CUR"]];
   if(studies.count!=1){NSLog(@"PREVIOUS_ROUTING_INVALID_DATABASE count=%lu",studies.count);return;}
   NSMutableArray *images=[NSMutableArray new];for(id series in [studies[0] valueForKey:@"series"])[images addObjectsFromArray:[[series valueForKey:@"images"] allObjects]];
   NSDictionary *config=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:[directory stringByAppendingPathComponent:@"config.json"]] options:0 error:NULL];
   NSMutableDictionary *arguments=[[NSUserDefaults.standardUserDefaults volatileDomainForName:NSArgumentDomain] mutableCopy];
   if(!arguments)arguments=[NSMutableDictionary new];arguments[@"SERVERS"]=config[@"servers"];
   [NSUserDefaults.standardUserDefaults setVolatileDomain:arguments forName:NSArgumentDomain];
   NSLog(@"PREVIOUS_ROUTING_APPLY images=%lu",images.count);
   [db applyRoutingRules:config[@"rules"] toImages:images];
   dispatch_after(dispatch_time(DISPATCH_TIME_NOW,25*NSEC_PER_SEC),dispatch_get_main_queue(),^{
    NSLog(@"PREVIOUS_ROUTING_REPEAT");[db applyRoutingRules:config[@"rules"] toImages:images];
   });
  });
 }];
}
