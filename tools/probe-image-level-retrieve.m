// A study retrieved when part of it is already local, from inside the development
// app (#634): the query window's retrieve with smart mode on, so the move takes the
// IMAGE-level route for the missing instances. Injected with DYLD_INSERT_LIBRARIES.
//
//   HOROS_RETRIEVE_SERVERS   JSON list with one DICOM node (Address, Port, AETitle,
//                            TransferSyntax, retrieveMode)
//   HOROS_RETRIEVE_TRIGGER   start once this file exists
//   HOROS_RETRIEVE_LOG       JSON lines
//   HOROS_RETRIEVE_CANCEL_AFTER_ARRIVAL  cancel the retrieve, as the activity window's
//                            button does, as soon as its first image has arrived (optional)
//   HOROS_RETRIEVE_CANCEL_AFTER  seconds; cancel the retrieve as the activity
//                            window's button does (optional)
//   HOROS_RETRIEVE_IMPORT_DELAY  delay the first received batch while it holds
//                            the real import lock (seconds, optional)
//   HOROS_RETRIEVE_SHOW_ERRORS   let the retrieve report its failures, as the query
//                            window does (optional): the result then says how long the
//                            main thread took to run a block in its default run loop
//                            mode - a modal alert holds that mode (#691) - and what the
//                            notices panel shows
//   HOROS_RETRIEVE_REPEAT    retrieve the study a second time once the first has been
//                            recorded, as a user asking again does (optional, #692)
//
// Lines: {"started": {...}}, then {"retrieve": {...}} once the retrieve thread has
// finished and 8 s more have passed: when it finished, the study's local instance count
// (its SOP instances, not the SR objects the app archives for it)
// at that moment and at the end, when the last image arrived relative to the finish,
// the cancellation time if any, and the retrieve inventory the move left. With
// HOROS_RETRIEVE_REPEAT, {"retrieve_again": {...}} follows for the second retrieve.
//
//   xcrun clang -dynamiclib -fobjc-arc -framework Cocoa tools/probe-image-level-retrieve.m -o probe.dylib
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>
#include <stdatomic.h>

@interface NSObject (ImageLevelRetrieveProbe)
+ (id)activeLocalDatabase;
+ (id)defaultManager;
- (NSArray *)objectsForEntity:(id)entity predicate:(NSPredicate *)predicate;
- (id)initWithDataset:(void *)d callingAET:(id)a calledAET:(id)b hostname:(id)c port:(int)p transferSyntax:(int)t
          compression:(float)f extraParameters:(id)e;
- (id)initWithCallingAET:(id)a distantServer:(id)s;
- (id)initWithWindow:(id)w;
- (void)setShowErrorMessage:(BOOL)b;
- (void)setNoSmartMode:(BOOL)b;
- (void)queryWithValues:(id)v;
- (NSArray *)children;
- (void)performRetrieve:(NSArray *)a;
- (void)addThreadAndStart:(NSThread *)t;
- (void)setStatus:(NSString *)s;
- (void)setSupportsCancel:(BOOL)b;
- (void)setIsCancelled:(BOOL)b;
- (NSString *)uid;
- (id)retrieveInventory;
- (NSUInteger)countOfSuccessfulSuboperations;
- (NSUInteger)countOfSuboperations;
@end

static NSString *logPath;
static NSString *retrieveTrigger;
static double importDelay;
static atomic_bool delayedImport;
static NSArray *(*originalAddFiles)(id, SEL, NSArray *, BOOL, BOOL, BOOL, BOOL, BOOL);
static atomic_int noticesPosted;
static void (*originalPostNotice)(id, SEL, NSString *, NSString *);

// Every notice posted, repeats included: the panel counts a repeat on the notice
// already listed, so its row count does not show one.
static void countedPostNotice(id notices, SEL selector, NSString *title, NSString *message) {
    atomic_fetch_add(&noticesPosted, 1);
    originalPostNotice(notices, selector, title, message);
}

static NSArray *delayedAddFiles(id database, SEL selector, NSArray *files, BOOL notifications,
                               BOOL reread, BOOL generated, BOOL imported, BOOL returnArray) {
    if ([NSFileManager.defaultManager fileExistsAtPath:retrieveTrigger]) {
        static dispatch_once_t once;
        dispatch_once(&once, ^{
            atomic_store(&delayedImport, true);
            [NSThread sleepForTimeInterval:importDelay];
        });
    }
    return originalAddFiles(database, selector, files, notifications, reread, generated, imported, returnArray);
}

static void writeLine(NSDictionary *object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    NSFileHandle *handle = [NSFileHandle fileHandleForWritingAtPath:logPath];
    if (!handle) {
        [[NSData data] writeToFile:logPath atomically:NO];
        handle = [NSFileHandle fileHandleForWritingAtPath:logPath];
    }
    [handle seekToEndOfFile];
    [handle writeData:data];
    [handle writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
    [handle closeFile];
}

static double uptime(void) { return NSProcessInfo.processInfo.systemUptime; }

// Milliseconds the main thread took to run a block queued for its default run loop
// mode, or -1 when it did not within `timeout` seconds: what the import hands to the
// main thread with -performSelectorOnMainThread: waits for that mode.
static double mainDefaultModeLatency(double timeout) {
    atomic_bool *ran = calloc(1, sizeof(atomic_bool));
    double start = uptime();
    CFRunLoopPerformBlock(CFRunLoopGetMain(), kCFRunLoopDefaultMode, ^{ atomic_store(ran, true); });
    CFRunLoopWakeUp(CFRunLoopGetMain());
    while (!atomic_load(ran) && uptime() - start < timeout) usleep(5000);
    double latency = atomic_load(ran) ? (uptime() - start) * 1000 : -1;
    if (latency >= 0) free(ran);  // otherwise the block may still run later
    return latency;
}

// The study's instances held locally: a multiframe instance is one image per frame in the
// index, and the SR objects the app archives for the study are not the study's.
static NSUInteger localImages(NSString *studyUID) {
    __block NSUInteger count = 0;
    dispatch_sync(dispatch_get_main_queue(), ^{
        id database = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
        NSArray *images = [database objectsForEntity:@"Image"
                                           predicate:[NSPredicate predicateWithFormat:@"series.study.studyInstanceUID == %@ AND series.modality != %@",
                                                      studyUID, @"SR"]];
        count = [[NSSet setWithArray:[images valueForKey:@"sopInstanceUID"]] count];
    });
    return count;
}

__attribute__((constructor)) static void installImageLevelRetrieveProbe(void) {
    NSDictionary *environment = NSProcessInfo.processInfo.environment;
    NSString *serversPath = environment[@"HOROS_RETRIEVE_SERVERS"], *trigger = environment[@"HOROS_RETRIEVE_TRIGGER"];
    logPath = environment[@"HOROS_RETRIEVE_LOG"];
    double cancelAfter = [environment[@"HOROS_RETRIEVE_CANCEL_AFTER"] doubleValue];
    BOOL cancelAfterArrival = environment[@"HOROS_RETRIEVE_CANCEL_AFTER_ARRIVAL"] != nil;
    BOOL showErrors = environment[@"HOROS_RETRIEVE_SHOW_ERRORS"] != nil;
    int attempts = environment[@"HOROS_RETRIEVE_REPEAT"] != nil ? 2 : 1;
    importDelay = [environment[@"HOROS_RETRIEVE_IMPORT_DELAY"] doubleValue];
    retrieveTrigger = trigger;
    if (!serversPath || !trigger || !logPath) return;
    unsetenv("DYLD_INSERT_LIBRARIES");
    writeLine(@{@"probe": @"loaded"});
    [NSNotificationCenter.defaultCenter addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil
                                                     queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        if (importDelay > 0) {
            Method method = class_getInstanceMethod(NSClassFromString(@"DicomDatabase"),
                NSSelectorFromString(@"addFilesDescribedInDictionaries:postNotifications:rereadExistingItems:generatedByOsiriX:importedFiles:returnArray:"));
            if (method) originalAddFiles = (void *)method_setImplementation(method, (IMP)delayedAddFiles);
        }
        Method post = class_getClassMethod(NSClassFromString(@"HorosNetworkNotices"), NSSelectorFromString(@"postTitle:message:"));
        if (post) originalPostNotice = (void *)method_setImplementation(post, (IMP)countedPostNotice);
        [NSThread detachNewThreadWithBlock:^{
            @autoreleasepool {
                while (![NSFileManager.defaultManager fileExistsAtPath:trigger]) usleep(50000);
                NSDictionary *server = [[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:serversPath]
                                                                         options:0 error:NULL] firstObject];
                id root = [[NSClassFromString(@"DCMTKRootQueryNode") alloc] initWithDataset:NULL callingAET:@"HOROSDEV"
                                                                                  calledAET:server[@"AETitle"] hostname:@"127.0.0.1"
                                                                                       port:[server[@"Port"] intValue] transferSyntax:0
                                                                                compression:0 extraParameters:server];
                [root setShowErrorMessage:NO];
                [root queryWithValues:@[]];
                id study = [[root children] firstObject];
                if (!study) {
                    writeLine(@{@"retrieve": @{@"error": @"no study"}});
                    return;
                }
                NSString *studyUID = [study uid];
                for (int attempt = 0; attempt < attempts; attempt++) {
                // Smart mode: the move looks at what is already local and asks the
                // IMAGE level for the rest.
                [study setNoSmartMode:NO];
                [study setShowErrorMessage:showErrors];
                NSUInteger before = localImages(studyUID);
                __block NSThread *thread = nil;
                __block id controller = nil;
                dispatch_sync(dispatch_get_main_queue(), ^{
                    controller = [[NSClassFromString(@"QueryController") alloc] initWithWindow:nil];
                    id manager = [[NSClassFromString(@"QueryArrayController") alloc] initWithCallingAET:@"HOROSDEV" distantServer:server];
                    [controller setValue:manager forKey:@"queryManager"];
                    thread = [[NSThread alloc] initWithTarget:controller selector:@selector(performRetrieve:) object:@[study]];
                    thread.name = @"Retrieving images...";
                    [thread setStatus:@"1 study"];
                    [thread setSupportsCancel:YES];
                    [[NSClassFromString(@"ThreadsManager") defaultManager] addThreadAndStart:thread];
                });
                double start = uptime();
                writeLine(@{@"started": @{@"study": studyUID ?: @"", @"local_before": @(before), @"at": @(start)}});
                double cancelledAt = -1, finishedAt = -1, lastArrival = start;
                NSUInteger count = before, atFinish = 0;
                for (;;) {
                    usleep(20000);
                    NSUInteger now = localImages(studyUID);
                    if (now != count) { count = now; lastArrival = uptime(); }
                    BOOL due = (cancelAfter > 0 && uptime() - start >= cancelAfter) || (cancelAfterArrival && count > before);
                    if (due && cancelledAt < 0 && !thread.isFinished) {
                        dispatch_sync(dispatch_get_main_queue(), ^{
                            // What -[ThreadCell cancelThreadAction:] does.
                            [thread setStatus:@"Cancelling..."];
                            [thread setIsCancelled:YES];
                        });
                        cancelledAt = uptime();
                    }
                    if (finishedAt < 0 && thread.isFinished) { finishedAt = uptime(); atFinish = count; }
                    if (finishedAt >= 0 && uptime() - finishedAt >= 8) break;
                    if (uptime() - start > 180) break;
                }
                id inventory = [study retrieveInventory];
                NSMutableDictionary *result = [@{@"finished": @(finishedAt >= 0), @"seconds": @(finishedAt >= 0 ? finishedAt - start : -1),
                                                 @"local_before": @(before), @"local_at_finish": @(atFinish), @"local_after": @(count),
                                                 @"last_arrival_after_finish": @(finishedAt >= 0 ? lastArrival - finishedAt : -1),
                                                 @"cancelled_at": @(cancelledAt >= 0 ? cancelledAt - start : -1),
                                                 @"finish_after_cancel": @(cancelledAt >= 0 && finishedAt >= 0 ? finishedAt - cancelledAt : -1),
                                                 @"received": @([study countOfSuccessfulSuboperations]),
                                                 @"import_delay_applied": @(atomic_load(&delayedImport)),
                                                 @"expected": @([study countOfSuboperations])} mutableCopy];
                if (inventory) {
                    // needsAttention is what raises «Retrieve Incomplete» when error messages are shown (#646).
                    // Only the keys this build's inventory has: receivedAwaitingImportCount came with #646.
                    NSMutableArray *keys = [NSMutableArray array];
                    for (NSString *key in @[@"inventoryConfirmed", @"expectedCount", @"importedCount", @"isComplete",
                                            @"needsAttention", @"receivedAwaitingImportCount", @"unsendableUIDs", @"summary"])
                        if ([inventory respondsToSelector:NSSelectorFromString(key)]) [keys addObject:key];
                    result[@"inventory"] = [inventory dictionaryWithValuesForKeys:keys];
                }
                if (showErrors) {
                    result[@"main_default_mode_ms"] = @(mainDefaultModeLatency(5));
                    dispatch_sync(dispatch_get_main_queue(), ^{
                        Class notices = NSClassFromString(@"HorosNetworkNotices");
                        result[@"notices"] = notices ? [notices valueForKey:@"noticeCount"] : @(-1);
                        result[@"notices_showing"] = notices ? [notices valueForKey:@"isShowing"] : @NO;
                    });
                    result[@"notices_posted"] = @(atomic_load(&noticesPosted));
                }
                writeLine(@{(attempt ? @"retrieve_again" : @"retrieve"): result});
                }
            }
        }];
    }];
}
