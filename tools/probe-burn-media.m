// Prepares a medium from inside the development app (#632): the burn window's own
// controller, destination a disc image, every image of the active local database.
// Injected with DYLD_INSERT_LIBRARIES.
//
//   HOROS_BURN_TRIGGER   a path: start once that file exists
//   HOROS_BURN_DMG       where the disc image goes (the save panel answers with it)
//   HOROS_BURN_LOG       a JSON lines file
//   HOROS_BURN_ESTIMATES how many times to time -estimateFolderSize: (default 50)
//
// Lines written: {"estimate": {"text", "us": [...]}} - the size field's text and
// the time of each estimate - then {"burn": {...}} when the burn has ended: the
// seconds from -burn: to the end, whether the disc image exists, and the text of
// any alert the window raised instead (a failure is shown, not a success).
//
//   xcrun clang -dynamiclib -fobjc-arc -framework Cocoa tools/probe-burn-media.m -o probe-burn-media.dylib
#import <Cocoa/Cocoa.h>
#include <objc/runtime.h>
#include <mach/mach_time.h>

@interface NSObject (BurnMediaProbe)
+ (id)activeLocalDatabase;
- (NSArray *)objectsForEntity:(id)entity;
- (id)entityForName:(NSString *)name;
- (id)initWithFiles:(NSArray *)files managedObjects:(NSArray *)objects;
- (IBAction)burn:(id)sender;
- (IBAction)estimateFolderSize:(id)sender;
- (BOOL)buttonsDisabled;
@end

static NSString *logPath, *dmgPath;

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

static double microseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1000.0;
}

// Runs a block on the main thread and waits for it. A run loop block in the common
// modes, not dispatch_sync: the window raises a failure with -[NSAlert runModal]
// inside a main queue block, and the main queue runs nothing else until that alert
// is dismissed, so a dispatch_sync would wait for it forever (#639).
static void onMainThread(void (^block)(void)) {
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    CFRunLoopPerformBlock(CFRunLoopGetMain(), kCFRunLoopCommonModes, ^{
        block();
        dispatch_semaphore_signal(done);
    });
    CFRunLoopWakeUp(CFRunLoopGetMain());
    dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);
}

// The text of every visible alert, its fields at any depth.
static NSString *alertText(void) {
    NSMutableArray *texts = [NSMutableArray array];
    for (NSWindow *window in NSApp.windows) {
        if (!window.isVisible || ![window.className containsString:@"Alert"]) continue;
        NSMutableArray *views = [NSMutableArray arrayWithObject:window.contentView];
        while (views.count) {
            NSView *view = views.lastObject;
            [views removeLastObject];
            if ([view isKindOfClass:NSTextField.class] && [(NSTextField *)view stringValue].length)
                [texts addObject:[(NSTextField *)view stringValue]];
            [views addObjectsFromArray:view.subviews];
        }
    }
    return texts.count ? [texts componentsJoinedByString:@" | "] : nil;
}

// The save panel of a DMG burn: answered with HOROS_BURN_DMG, never shown.
static NSModalResponse answerSavePanel(id panel, SEL selector) { return NSModalResponseOK; }
static NSURL *savePanelURL(id panel, SEL selector) { return [NSURL fileURLWithPath:dmgPath]; }

__attribute__((constructor)) static void installBurnMediaProbe(void) {
    NSDictionary *environment = NSProcessInfo.processInfo.environment;
    NSString *trigger = environment[@"HOROS_BURN_TRIGGER"];
    dmgPath = environment[@"HOROS_BURN_DMG"];
    logPath = environment[@"HOROS_BURN_LOG"];
    NSInteger estimates = environment[@"HOROS_BURN_ESTIMATES"] ? [environment[@"HOROS_BURN_ESTIMATES"] integerValue] : 50;
    if (!trigger || !dmgPath || !logPath) return;
    unsetenv("DYLD_INSERT_LIBRARIES");
    method_setImplementation(class_getInstanceMethod(NSSavePanel.class, @selector(runModal)), (IMP)answerSavePanel);
    method_setImplementation(class_getInstanceMethod(NSSavePanel.class, @selector(URL)), (IMP)savePanelURL);
    writeLine(@{@"probe": @"loaded"});
    [NSNotificationCenter.defaultCenter addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil
                                                     queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        [NSThread detachNewThreadWithBlock:^{
            @autoreleasepool {
                for (int wait = 0; wait < 3000 && ![NSFileManager.defaultManager fileExistsAtPath:trigger]; wait++)
                    usleep(100000);
                __block id controller = nil;
                __block NSMutableDictionary *estimate = [NSMutableDictionary dictionary];
                onMainThread(^{
                    id database = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
                    NSArray *images = [database objectsForEntity:[database entityForName:@"Image"]];
                    NSArray *paths = [images valueForKey:@"completePath"];
                    NSArray *identifiers = [images valueForKey:@"objectID"];
                    controller = [[NSClassFromString(@"BurnerWindowController") alloc] initWithFiles:paths managedObjects:identifiers];
                    [controller showWindow:nil];
                    NSMutableArray *times = [NSMutableArray array];
                    for (NSInteger i = 0; i < estimates; i++) {
                        uint64_t t0 = mach_absolute_time();
                        [controller estimateFolderSize:nil];
                        [times addObject:@(microseconds(t0, mach_absolute_time()))];
                    }
                    NSTextField *field = [controller valueForKey:@"sizeField"];
                    estimate[@"text"] = field.stringValue ?: @"";
                    estimate[@"us"] = times;
                    estimate[@"files"] = @(paths.count);
                });
                writeLine(@{@"estimate": estimate});
                uint64_t start = mach_absolute_time();
                onMainThread(^{ [controller burn:nil]; });
                // The burn runs on a thread of its own; the window disables its
                // buttons meanwhile and enables them again at the end, success or not.
                usleep(300 * 1000);
                __block BOOL busy = YES;
                __block NSString *alert = nil;
                for (int wait = 0; wait < 1200 && busy; wait++) {
                    usleep(100 * 1000);
                    onMainThread(^{
                        busy = [controller buttonsDisabled];
                        alert = alertText() ?: alert;
                    });
                }
                usleep(500 * 1000);
                onMainThread(^{ alert = alertText() ?: alert; });
                writeLine(@{@"burn": @{@"seconds": @(microseconds(start, mach_absolute_time()) / 1e6), @"finished": @(!busy),
                                       @"dmg_exists": @([NSFileManager.defaultManager fileExistsAtPath:dmgPath]),
                                       @"alert": alert ?: [NSNull null]}});
            }
        }];
    }];
}
