// Diagnostic-only probe of native study-UID filters and the real Horos URL route.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>
@interface NSObject (UIDListProbe)
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
+ (NSArray*)queryStudyInstanceUID:(NSString*)value server:(NSDictionary*)server showErrors:(BOOL)show;
+ (id)sharedAppController;
- (void)getUrl:(NSAppleEventDescriptor*)event withReplyEvent:(NSAppleEventDescriptor*)reply;
@end
__attribute__((constructor)) static void install(void) {
    if (!getenv("HOROS_UID_LIST_PROBE")) return;
    // Keep the real URL parsing, XML-RPC dispatch and C-FIND; capture the
    // resulting studies instead of starting unrelated pixel retrievals.
    Method method = class_getInstanceMethod(NSClassFromString(@"XMLRPCInterface"), NSSelectorFromString(@"_threadRetrieve:"));
    if (!method) return;
    method_setImplementation(method, imp_implementationWithBlock(^(id object, NSDictionary *request){
        NSLog(@"UID_LIST_URL_RESULT %@", [[request objectForKey:@"children"] valueForKey:@"uid"]);
    }));
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3*NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            id db=[NSClassFromString(@"DicomDatabase") activeLocalDatabase];
            if (![[db dataBaseDirPath] containsString:@"/local-validation/"]) return;
            NSString *path=[NSString stringWithUTF8String:getenv("HOROS_UID_LIST_PROBE")];
            NSArray *uids=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:path] options:0 error:NULL];
            if (uids.count != 4) return;
            NSDictionary *server=@{@"Description":@"UIDLISTFIX", @"Address":@"127.0.0.1", @"Port":@11199,
                @"AETitle":@"CFINDFIX", @"TransferSyntax":@0, @"retrieveMode":@0, @"Activated":@YES, @"QR":@YES};
            NSUserDefaults *defaults=NSUserDefaults.standardUserDefaults;
            NSMutableDictionary *arguments=[[defaults volatileDomainForName:NSArgumentDomain] mutableCopy];
            arguments[@"SERVERS"]=@[server]; arguments[@"httpXMLRPCServer"]=@YES;
            [defaults setVolatileDomain:arguments forName:NSArgumentDomain];
            NSArray *cases=@[
                [NSString stringWithFormat:@"  %@\\%@\n",uids[0],uids[1]],
                [NSString stringWithFormat:@"%@\\1.2.826.0.1.3680043.10.543.169.999",uids[2]]];
            for (NSUInteger index=0; index<cases.count; index++) {
                NSTextField *field=[[NSTextField alloc] initWithFrame:NSMakeRect(0,0,500,22)];
                field.stringValue=cases[index];
                NSArray *answers=[NSClassFromString(@"QueryController") queryStudyInstanceUID:field.stringValue server:server showErrors:NO];
                NSLog(@"UID_LIST_FIELD_RESULT %lu %@", index, [answers valueForKey:@"uid"]);
            }
            NSString *encoded=[NSString stringWithFormat:@"%@%%5C%@%%5C%@",uids[0],uids[2],uids[3]];
            NSString *url=[@"horos://?methodName=Retrieve&serverName=UIDLISTFIX&filterKey=StudyInstanceUID&filterValue=" stringByAppendingString:encoded];
            NSAppleEventDescriptor *event=[NSAppleEventDescriptor appleEventWithEventClass:kInternetEventClass eventID:kAEGetURL targetDescriptor:nil returnID:kAutoGenerateReturnID transactionID:kAnyTransactionID];
            [event setParamDescriptor:[NSAppleEventDescriptor descriptorWithString:url] forKeyword:keyDirectObject];
            [[NSClassFromString(@"AppController") sharedAppController] getUrl:event withReplyEvent:nil];
            NSLog(@"UID_LIST_DISPATCH_DONE");
        });
    }];
}
