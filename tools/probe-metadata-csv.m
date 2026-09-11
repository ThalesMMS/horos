// Diagnostic-only probe for #146: run the metadata export without the save panel.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-metadata-csv.m \
//     -o local-validation/work/csv146/probe.dylib
//
// HOROS_METADATA_CSV=<path to write> and the columns in HOROS_METADATA_COLUMNS,
// separated by commas. The panel is the only thing skipped: the rows come from
// -[BrowserController metadataCSVForColumns:onlySelected:], which is what the
// menu item calls.
#import <Cocoa/Cocoa.h>

@interface NSObject (MetadataCSVProbe)
+ (id)currentBrowser;
- (NSString*)metadataCSVForColumns:(NSArray*)columns onlySelected:(BOOL)onlySelected;
+ (NSData*)dataForCSV:(NSString*)text;
@end

__attribute__((constructor)) static void install(void) {
    const char *destination = getenv("HOROS_METADATA_CSV");
    if (!destination) return;
    if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"]) return;
    NSString *path = [NSString stringWithUTF8String:destination];
    const char *wanted = getenv("HOROS_METADATA_COLUMNS");
    NSArray *columns = wanted ? [[NSString stringWithUTF8String:wanted] componentsSeparatedByString:@","]
                              : @[@"PatientName", @"PatientID", @"StudyDescription",
                                  @"InstitutionName", @"AccessionNumber", @"(0008,0005)"];
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
                                                      object:nil queue:NSOperationQueue.mainQueue
                                                  usingBlock:^(NSNotification *n) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 12 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            id browser = [NSClassFromString(@"BrowserController") currentBrowser];
            if (![browser respondsToSelector:@selector(metadataCSVForColumns:onlySelected:)]) {
                NSLog(@"CSV146 the browser does not answer metadataCSVForColumns:onlySelected:");
                return;
            }
            NSString *csv = [browser metadataCSVForColumns:columns onlySelected:NO];
            NSError *error = nil;
            Class export = NSClassFromString(@"HorosStudyMetadataExport");
            NSData *data = [export dataForCSV:csv];
            BOOL written = [data writeToFile:path options:NSDataWritingAtomic error:&error];
            NSLog(@"CSV146 wrote %lu bytes to %@ (%d) %@", (unsigned long)data.length, path, written,
                  error.localizedDescription ?: @"");
        });
    }];
}
