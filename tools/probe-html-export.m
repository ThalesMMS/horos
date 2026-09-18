// Runs the database browser's movie/HTML export from inside the development app
// (#625), the export that scales every frame of a series to the movie's size with
// -[NSImage imageByScalingProportionallyToSize:].
//
//   HOROS_HTML_EXPORT_TRIGGER  a path: export once that file exists
//   HOROS_HTML_EXPORT_OUT      the folder the export writes into
//   HOROS_HTML_EXPORT_LOG      a JSON lines file: {"export": {...}} when done
//
// Every image of the active local database is exported, sorted by series and
// instance number, through +[BrowserController exportQuicktime::::] with HTML on,
// on a background thread - the way the burn window's HTML option calls it.
//
//   xcrun clang -dynamiclib -fobjc-arc -framework Cocoa tools/probe-html-export.m -o probe-html-export.dylib
#import <Cocoa/Cocoa.h>

@interface NSObject (HTMLExportProbe)
+ (id)activeLocalDatabase;
- (id)independentDatabase;
- (NSArray *)objectsForEntity:(id)entity;
- (id)entityForName:(NSString *)name;
+ (void)exportQuicktime:(NSArray *)files :(NSString *)path :(BOOL)html :(id)browser :(NSMutableDictionary *)seriesPaths;
@end

static void writeLine(NSString *path, NSDictionary *object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    NSFileHandle *handle = [NSFileHandle fileHandleForWritingAtPath:path];
    if (!handle) {
        [[NSData data] writeToFile:path atomically:NO];
        handle = [NSFileHandle fileHandleForWritingAtPath:path];
    }
    [handle seekToEndOfFile];
    [handle writeData:data];
    [handle writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
    [handle closeFile];
}

__attribute__((constructor)) static void installHTMLExportProbe(void) {
    NSDictionary *environment = NSProcessInfo.processInfo.environment;
    NSString *trigger = environment[@"HOROS_HTML_EXPORT_TRIGGER"], *out = environment[@"HOROS_HTML_EXPORT_OUT"],
             *log = environment[@"HOROS_HTML_EXPORT_LOG"];
    if (!trigger || !out || !log) return;
    unsetenv("DYLD_INSERT_LIBRARIES");
    [NSNotificationCenter.defaultCenter addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil
                                                     queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        [NSThread detachNewThreadWithBlock:^{
            @autoreleasepool {
                for (int wait = 0; wait < 3000 && ![NSFileManager.defaultManager fileExistsAtPath:trigger]; wait++)
                    usleep(100000);
                NSMutableDictionary *result = [NSMutableDictionary dictionary];
                double start = NSProcessInfo.processInfo.systemUptime;
                @try {
                    id database = [[NSClassFromString(@"DicomDatabase") activeLocalDatabase] independentDatabase];
                    NSArray *images = [database objectsForEntity:[database entityForName:@"Image"]];
                    images = [images sortedArrayUsingDescriptors:@[
                        [NSSortDescriptor sortDescriptorWithKey:@"series.id" ascending:YES],
                        [NSSortDescriptor sortDescriptorWithKey:@"instanceNumber" ascending:YES]]];
                    result[@"images"] = @(images.count);
                    [NSFileManager.defaultManager createDirectoryAtPath:out withIntermediateDirectories:YES attributes:nil error:NULL];
                    [NSClassFromString(@"BrowserController") exportQuicktime:images :out :YES :nil :nil];
                } @catch (NSException *e) {
                    result[@"exception"] = [NSString stringWithFormat:@"%@: %@", e.name, e.reason];
                }
                result[@"seconds"] = @(NSProcessInfo.processInfo.systemUptime - start);
                writeLine(log, @{@"export": result});
            }
        }];
    }];
}
