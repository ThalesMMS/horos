// Diagnostic only: synthetic local Orthanc, isolated development application/database.
#import <Cocoa/Cocoa.h>
@interface NSObject(DICOMwebProbe)
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
+ (BOOL)saveForIdentifier:(NSString*)identifier username:(NSString*)username password:(NSString*)password bearerToken:(NSString*)token error:(NSError**)error;
+ (BOOL)removeForIdentifier:(NSString*)identifier error:(NSError**)error;
- (id)initWithCallingAET:(NSString*)ae distantServer:(NSDictionary*)server;
- (void)performQuery:(BOOL)show;
- (NSArray*)queries;
- (NSArray*)children;
- (void)queryWithValues:(NSArray*)values;
- (void)move:(NSDictionary*)values retrieveMode:(int)mode;
- (unsigned long)countOfSuccessfulSuboperations;
@end
__attribute__((constructor)) static void install(void){
 if(!getenv("HOROS_DICOMWEB_CONFIG"))return;
 if(!getenv("HOROS_DICOMWEB_PROBE") || ![@[@"org.horosproject.horos.local-development", @"org.horosproject.horos.planar-performance"] containsObject:NSBundle.mainBundle.bundleIdentifier])return;
 int port=getenv("HOROS_DICOMWEB_PORT") ? atoi(getenv("HOROS_DICOMWEB_PORT")) : 18042;
 if(port<1024 || port>65535)return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
 if(![[[NSClassFromString(@"DicomDatabase") activeLocalDatabase] dataBaseDirPath] containsString:@"/local-validation/"])return;
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
 @autoreleasepool {
 NSString *path=[NSString stringWithUTF8String:getenv("HOROS_DICOMWEB_CONFIG")];
 NSDictionary*config=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:path] options:0 error:nil];
 NSDictionary*users=config[@"RegisteredUsers"];NSString*user=users.allKeys.firstObject;
 if(!user || ![users[user] isKindOfClass:NSString.class])return;
 NSString*identifier=NSUUID.UUID.UUIDString;Class store=NSClassFromString(@"HorosDICOMwebCredentials");NSError*error=nil;
 if(![store saveForIdentifier:identifier username:user password:users[user] bearerToken:@"" error:&error]){NSLog(@"DICOMWEB_PROBE credential failure");return;}
 @try {
 NSDictionary*server=@{@"Address":@"127.0.0.1",@"Port":@(port),@"AETitle":@"SYNTH197",@"Description":@"Synthetic DICOMweb",@"DICOMwebURL":[NSString stringWithFormat:@"http://127.0.0.1:%d/dicom-web",port],@"DICOMwebCredentialID":identifier,@"retrieveMode":@3};
 id manager=[[NSClassFromString(@"QueryArrayController") alloc] initWithCallingAET:@"SYNTH197" distantServer:server];
 [manager performQuery:NO];NSArray*studies=[manager queries];
 // A fresh synthetic node should have exactly one study. Never retrieve an
 // arbitrary first result from a node populated with unrelated studies.
 if(studies.count!=1){NSLog(@"DICOMWEB_PROBE expected one synthetic study, got %lu",(unsigned long)studies.count);[manager release];return;}
 id study=studies.firstObject;[study queryWithValues:nil];NSArray*series=[study children];
 id oneSeries=series.firstObject;[oneSeries queryWithValues:nil];NSArray*images=[oneSeries children];
 NSLog(@"DICOMWEB_NATIVE_QUERY studies=%lu series=%lu instances=%lu",(unsigned long)studies.count,(unsigned long)series.count,(unsigned long)images.count);
 [study move:@{@"retrieveMode":@3,@"study":study} retrieveMode:3];
 NSLog(@"DICOMWEB_NATIVE_RETRIEVE queued=%lu",[study countOfSuccessfulSuboperations]);
 [manager release];
 } @finally {NSLog(@"DICOMWEB_PROBE credential removed=%d",[store removeForIdentifier:identifier error:nil]);}
 }});
 }];
}
