// Diagnostic-only injection: enqueue copied synthetic fixtures in the real app.
// Build: clang -dynamiclib -fobjc-arc -framework Cocoa tools/probe-conversion-queue.m -o local-validation/work/conversion-probe.dylib
// Use only a development app signed by script/build_and_run.sh --diagnostics.
// Launch it with DYLD_INSERT_LIBRARIES=<probe> and HOROS_CONVERSION_PROBE_INPUT
// pointing to a directory of synthetic .dcm files. Set HOROS_CONVERSION_PROBE_MODE
// to compress to exercise the compression queue; the default is decompression. The active database must be
// under this checkout's local-validation directory. No UI interaction is injected.
#import <Cocoa/Cocoa.h>

@interface NSObject (HorosConversionProbe)
+ (id)activeLocalDatabase;
- (NSString *)dataBaseDirPath;
- (NSString *)decompressionDirPath;
- (void)kickstartCompressDecompress;
@end

__attribute__((constructor)) static void installConversionProbe(void)
{
    const char *input = getenv("HOROS_CONVERSION_PROBE_INPUT");
    if (!input) return;
    NSString *directory = [NSString stringWithUTF8String:input];
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
        object:nil queue:[NSOperationQueue mainQueue] usingBlock:^(NSNotification *note) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            id database = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
            if (![[database dataBaseDirPath] containsString:@"/local-validation/"]) {
                NSLog(@"CONVERSION_PROBE_REFUSED: active database is not disposable");
                return;
            }
            NSMutableArray *paths = [NSMutableArray array];
            NSFileManager *manager = [NSFileManager defaultManager];
            [manager createDirectoryAtPath:[database decompressionDirPath] withIntermediateDirectories:YES attributes:nil error:nil];
            for (NSString *name in [manager contentsOfDirectoryAtPath:directory error:nil]) {
                if (![name.pathExtension.lowercaseString isEqualToString:@"dcm"]) continue;
                NSString *source = [directory stringByAppendingPathComponent:name];
                NSString *target = [[database decompressionDirPath] stringByAppendingPathComponent:name];
                NSError *error = nil;
                if (![manager copyItemAtPath:source toPath:target error:&error]) {
                    NSLog(@"CONVERSION_PROBE_COPY_FAILED: %@: %@", name, error.localizedDescription);
                    return;
                }
                [paths addObject:target];
            }
            BOOL compress = getenv("HOROS_CONVERSION_PROBE_MODE") && !strcmp(getenv("HOROS_CONVERSION_PROBE_MODE"), "compress");
            NSMutableArray *queue = [database valueForKey:compress ? @"compressQueue" : @"decompressQueue"];
            @synchronized(queue) { [queue addObjectsFromArray:paths]; }
            [database kickstartCompressDecompress];
            NSLog(@"CONVERSION_PROBE_ENQUEUED: %lu", (unsigned long)paths.count);
        });
    }];
}
