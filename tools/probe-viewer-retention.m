// Diagnostic-only probe for #133: what a plugin's duplicate/close cycle retains.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-viewer-retention.m \
//     -o local-validation/work/retention133/probe.dylib
//
// HOROS_VIEWER_RETENTION=<cycles>. With a 2D viewer open, it calls the same
// -[ViewerController copyViewerWindow] that -[PluginFilter
// duplicateCurrent2DViewerWindow] calls, closes the copy, lets the run loop turn
// and an autorelease pool drain, and reports the live viewer count and the
// process's resident footprint each time. It opens nothing and deletes nothing.
#import <Cocoa/Cocoa.h>
#import <mach/mach.h>

@interface NSObject (ViewerRetentionProbe)
+ (NSMutableArray*)get2DViewers;
+ (NSMutableArray*)getDisplayed2DViewers;
- (id)copyViewerWindow;
- (void)close;
@end

static double residentMegabytes(void) {
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS)
        return -1;
    return (double)info.phys_footprint / (1024.0 * 1024.0);
}

// Turn the run loop the way returning to the event loop would, so anything
// waiting on an autorelease pool or a delayed perform gets its chance.
static void settle(double seconds) {
    @autoreleasepool {
        NSDate *until = [NSDate dateWithTimeIntervalSinceNow:seconds];
        while ([until timeIntervalSinceNow] > 0)
            [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode
                                     beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
    }
}

__attribute__((constructor)) static void install(void) {
    const char *wanted = getenv("HOROS_VIEWER_RETENTION");
    if (!wanted) return;
    if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"]) return;
    int cycles = atoi(wanted);
    if (cycles <= 0) cycles = 10;

    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
                                                      object:nil queue:NSOperationQueue.mainQueue
                                                  usingBlock:^(NSNotification *n) {
        __block BOOL ran = NO;
        NSTimer *wait = [NSTimer timerWithTimeInterval:3.0 repeats:YES block:^(NSTimer *timer) {
            if (ran) { [timer invalidate]; return; }
            Class viewerClass = NSClassFromString(@"ViewerController");
            NSArray *open = [viewerClass getDisplayed2DViewers];
            if (open.count == 0) return;
            ran = YES;

            id viewer = open.firstObject;
            settle(2.0);
            double baseline = residentMegabytes();
            NSUInteger baseCount = [[viewerClass get2DViewers] count];
            NSLog(@"RETAIN133 baseline: %lu viewer(s), %.1f MB resident",
                  (unsigned long)baseCount, baseline);

            double peak = baseline;
            for (int cycle = 1; cycle <= cycles; cycle++) {
                // No autorelease pool of this probe's own around the close. The
                // duplicate is autoreleased and its window is released when it
                // closes; draining a pool right after closing releases it again
                // and the next drain crashes in -[NSAutounbinder dealloc].
                // Measured: a pool here took the application down on the second
                // cycle. The contract is to close it and return to the event
                // loop, which is what settle() does.
                id copy = [viewer copyViewerWindow];
                settle(1.0);
                double afterCopy = residentMegabytes();
                if (afterCopy > peak) peak = afterCopy;
                NSUInteger duringCount = [[viewerClass get2DViewers] count];
                [copy close];
                copy = nil;
                settle(2.0);
                NSLog(@"RETAIN133 cycle %2d: %lu viewer(s) while open, %lu after closing, "
                      @"%.1f MB after copy, %.1f MB after close",
                      cycle, (unsigned long)duringCount,
                      (unsigned long)[[viewerClass get2DViewers] count],
                      afterCopy, residentMegabytes());
            }

            settle(4.0);
            double settled = residentMegabytes();
            NSLog(@"RETAIN133 after %d cycle(s): %lu viewer(s), %.1f MB resident "
                  @"(baseline %.1f, peak %.1f, difference %+.1f MB)",
                  cycles, (unsigned long)[[viewerClass get2DViewers] count], settled,
                  baseline, peak, settled - baseline);
            NSLog(@"RETAIN133 done");
            settle(12.0);
            NSLog(@"RETAIN133 post-drain ok");
        }];
        [NSRunLoop.mainRunLoop addTimer:wait forMode:NSRunLoopCommonModes];
    }];
}
