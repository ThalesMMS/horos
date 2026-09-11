// Diagnostic-only probe for #158: run the export by identifier list without the
// two panels.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-batch-export.m \
//     -o local-validation/work/batch158/probe.dylib
//
// HOROS_BATCH_IDENTIFIERS: the identifiers, separated by commas.
// HOROS_BATCH_DESTINATION: where to write.  HOROS_BATCH_DRY_RUN=1 to copy nothing.
// The panels are the only thing skipped: the work is
// -[BrowserController exportStudiesForIdentifiers:toDirectory:dryRun:].
#import <Cocoa/Cocoa.h>

@interface NSObject (BatchExportProbe)
+ (id)currentBrowser;
- (NSString*)exportStudiesForIdentifiers:(NSArray*)identifiers toDirectory:(NSString*)directory dryRun:(BOOL)dryRun;
@end

__attribute__((constructor)) static void install(void) {
    const char *wanted = getenv("HOROS_BATCH_IDENTIFIERS");
    const char *where = getenv("HOROS_BATCH_DESTINATION");
    if (!wanted || !where) return;
    if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"]) return;
    NSArray *identifiers = [[NSString stringWithUTF8String:wanted] componentsSeparatedByString:@","];
    NSString *directory = [NSString stringWithUTF8String:where];
    BOOL dryRun = getenv("HOROS_BATCH_DRY_RUN") != NULL;
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
                                                      object:nil queue:NSOperationQueue.mainQueue
                                                  usingBlock:^(NSNotification *n) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 12 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            id browser = [NSClassFromString(@"BrowserController") currentBrowser];
            if (![browser respondsToSelector:@selector(exportStudiesForIdentifiers:toDirectory:dryRun:)]) {
                NSLog(@"BATCH158 the browser does not answer exportStudiesForIdentifiers:toDirectory:dryRun:");
                return;
            }
            NSString *report = [browser exportStudiesForIdentifiers:identifiers toDirectory:directory dryRun:dryRun];
            NSLog(@"BATCH158 done, %lu characters of report", (unsigned long)report.length);
        });
    }];
}
