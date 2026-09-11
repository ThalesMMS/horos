// Diagnostic observer for #299; never linked into the application.
// Counts real DisplayStudy dispatches without replacing any handler or parser.
// Load only in a development bundle with an isolated database and synthetic data.
#import <Cocoa/Cocoa.h>

__attribute__((constructor)) static void installSchemeProbe(void) {
    const char *output = getenv("HOROS_SCHEME_PROBE_OUT");
    if (!output) return;
    NSString *path = [NSString stringWithUTF8String:output];
    if (![path containsString:@"/local-validation/"]) return;
    [[NSNotificationCenter defaultCenter]
        addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil
        queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *notification) {
        if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"])
            return;
        if (![[NSUserDefaults.standardUserDefaults stringForKey:@"DATABASELOCATIONURL"] containsString:@"/local-validation/"])
            return;
        __block NSUInteger count = 0;
        void (^record)(BOOL) = ^(BOOL encodedParametersMatch) {
            NSDictionary *result = @{@"displayStudyDispatches": @(count),
                                     @"encodedParametersMatch": @(encodedParametersMatch)};
            NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:NULL];
            [data writeToFile:path atomically:YES];
        };
        record(NO);
        [[NSNotificationCenter defaultCenter]
            addObserverForName:@"OsiriXXMLRPCMessage" object:nil
            queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *event) {
            NSDictionary *parameters = event.object;
            if (![[parameters[@"methodName"] lowercaseString] isEqualToString:@"displaystudy"])
                return;
            count++;
            record([parameters[@"PatientID"] isEqualToString:@"LOCAL-URL+QA&é Тест"]);
        }];
    }];
}
