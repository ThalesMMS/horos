// A burst of scroll events on the 3D MPR, from inside the development app (#611), injected with
// DYLD_INSERT_LIBRARIES and driven by numbered command files.
//
//   HOROS_MPR_COMMANDS  a folder: <n>.json is run for n = 1, 2, ... in order, and answered in
//                       <n>.out.json (written whole, then renamed)
//
//   {"action": "ping"}
//   {"action": "open", "series": "<SeriesInstanceUID>", "mode": 1, "thickness_mm": 1, "wl": 40, "ww": 400,
//    "metal": true|false}
//       the series opened as the browser opens it, then its 3D MPR (-openMPRViewer, as the toolbar does):
//       clipping mode (1 MIP), slab thickness, WL/WW on the three views, 100 % (-actualSize:), Use Metal in
//       MPR as asked; with "fill_screen" the window takes the screen's visible frame first. Answers the
//       window number and each view's frame in screen points, top-left origin.
//   {"action": "burst", "view": 1|2|3, "events": 120, "delta": 1.5, "first": 1|-1, "interval_ms": 0}
//       that many scroll-wheel events (line units, deltaY alternating +delta and -delta, starting with
//       first) sent to the view's -scrollWheel:, each in a block of its own on the main queue, interval_ms
//       apart, so the run loop can draw between them as it does for input. Answers when the last one has
//       been handled, with the time each took.
//   {"action": "state"}
//       per view: the reconstructed plane (DCMPix) size and the mean of its central quarter; how many times
//       the view drew since the probe was loaded and how long ago the last draw was; whether it needs
//       display, is hidden, and its window is visible; the controller's lowLOD.
//
//   xcrun clang -dynamiclib -fobjc-arc -framework Cocoa tools/probe-mpr-scroll-burst.m -o probe-mpr-scroll-burst.dylib
#import <Cocoa/Cocoa.h>
#include <mach/mach_time.h>
#include <objc/message.h>
#include <objc/runtime.h>

@interface NSObject (MPRScrollBurstProbe)
+ (id)activeLocalDatabase;
+ (id)currentBrowser;
- (NSArray *)objectsForEntity:(id)entity;
- (id)entityForName:(NSString *)name;
- (id)loadSeries:(id)series :(id)viewer :(BOOL)firstViewer keyImagesOnly:(BOOL)keyImages;
- (BOOL)isEverythingLoaded;
- (id)openMPRViewer;
- (id)mprView1;
- (id)mprView2;
- (id)mprView3;
- (void)setClippingRangeMode:(int)mode;
- (void)setClippingRangeThicknessInMm:(float)thickness;
- (void)setWLWW:(float)wl :(float)ww;
- (IBAction)actualSize:(id)sender;
- (BOOL)horosMPRMetalEnabled;
- (void)toggleMPRMetal:(id)sender;
- (id)curDCM;
- (float *)fImage;
- (long)pwidth;
- (long)pheight;
- (BOOL)lowLOD;
@end

static id mprController = nil;
static NSMutableDictionary<NSValue *, NSNumber *> *drawCounts;
static NSMutableDictionary<NSValue *, NSNumber *> *lastDraws;
static IMP originalDrawRect;

static double nowMs(void) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)mach_absolute_time() * timebase.numer / timebase.denom / 1e6;
}

static id onMain(id (^block)(void)) {
    __block id result = nil;
    if ([NSThread isMainThread]) return block();
    dispatch_sync(dispatch_get_main_queue(), ^{ result = block(); });
    return result;
}

// Every draw of an MPR view, counted and timed: whether the view drew after the burst, and when.
static void countedDrawRect(id view, SEL selector, NSRect rect) {
    if ([view isKindOfClass:NSClassFromString(@"MPRDCMView")]) {
        NSValue *key = [NSValue valueWithPointer:(__bridge void *)view];
        drawCounts[key] = @(drawCounts[key].integerValue + 1);
        lastDraws[key] = @(nowMs());
    }
    ((void (*)(id, SEL, NSRect))originalDrawRect)(view, selector, rect);
}

static NSArray *views(void) {
    return mprController ? @[[mprController mprView1], [mprController mprView2], [mprController mprView3]] : @[];
}

// A view's frame on the screen, in points with the origin at the top left, as screencapture -R takes it.
static NSDictionary *screenFrame(NSView *view) {
    NSRect inWindow = [view convertRect:view.bounds toView:nil];
    NSRect onScreen = [view.window convertRectToScreen:inWindow];
    CGFloat top = NSMaxY(NSScreen.screens.firstObject.frame);
    return @{@"x": @(onScreen.origin.x), @"y": @(top - NSMaxY(onScreen)), @"width": @(onScreen.size.width),
             @"height": @(onScreen.size.height)};
}

static NSDictionary *openMPR(NSDictionary *command) {
    id viewer = onMain(^id {
        id database = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
        for (id series in [database objectsForEntity:[database entityForName:@"Series"]])
            if ([[series valueForKey:@"seriesDICOMUID"] isEqualToString:command[@"series"]])
                return [[NSClassFromString(@"BrowserController") currentBrowser] loadSeries:series :nil :YES keyImagesOnly:NO];
        return nil;
    });
    if (!viewer) return @{@"error": @"no such series"};
    for (int wait = 0; wait < 1200 && ![onMain(^id { return @([viewer isEverythingLoaded]); }) boolValue]; wait++)
        usleep(50 * 1000);
    usleep(300 * 1000);
    id opened = onMain(^id {
        mprController = [viewer openMPRViewer];
        if (!mprController) return @{@"error": @"no 3D MPR window"};
        [mprController showWindow:nil];
        NSWindow *window = [mprController window];
        if ([command[@"fill_screen"] boolValue])
            [window setFrame:window.screen.visibleFrame display:YES];
        [window makeKeyAndOrderFront:nil];
        return @{@"ok": @YES};
    });
    if (![opened[@"ok"] boolValue]) return opened;
    usleep(1500 * 1000);
    return onMain(^id {
        BOOL metal = [command[@"metal"] boolValue];
        if ([mprController respondsToSelector:@selector(horosMPRMetalEnabled)] && [mprController horosMPRMetalEnabled] != metal)
            [mprController toggleMPRMetal:nil];
        [mprController setClippingRangeMode:[command[@"mode"] intValue]];
        [mprController setClippingRangeThicknessInMm:[command[@"thickness_mm"] floatValue]];
        NSMutableArray *frames = [NSMutableArray array];
        for (id view in views()) {
            [view actualSize:nil];
            [view setWLWW:[command[@"wl"] floatValue] :[command[@"ww"] floatValue]];
            [frames addObject:screenFrame(view)];
        }
        NSWindow *window = [mprController window];
        return @{@"ok": @YES, @"window": @(window.windowNumber), @"frames": frames,
                 @"backing_scale": @(window.backingScaleFactor),
                 @"metal": @([mprController respondsToSelector:@selector(horosMPRMetalEnabled)] && [mprController horosMPRMetalEnabled])};
    });
}

static NSDictionary *burst(NSDictionary *command) {
    if (!mprController) return @{@"error": @"no 3D MPR window"};
    NSInteger events = [command[@"events"] integerValue];
    double delta = [command[@"delta"] doubleValue];
    int direction = [command[@"first"] intValue] < 0 ? -1 : 1;
    double interval = [command[@"interval_ms"] doubleValue];
    id view = views()[MAX(0, MIN(2, [command[@"view"] intValue] - 1))];
    NSMutableArray *handled = [NSMutableArray array];
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    double start = nowMs();
    for (NSInteger index = 0; index < events; index++) {
        double sign = (index % 2 == 0 ? direction : -direction);
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(interval * index * NSEC_PER_MSEC)), dispatch_get_main_queue(), ^{
            CGEventRef cg = CGEventCreateScrollWheelEvent(NULL, kCGScrollEventUnitLine, 1, 0);
            CGEventSetDoubleValueField(cg, kCGScrollWheelEventFixedPtDeltaAxis1, sign * delta);
            CGEventSetIntegerValueField(cg, kCGScrollWheelEventDeltaAxis1, (int64_t)lround(sign * delta));
            NSEvent *event = [NSEvent eventWithCGEvent:cg];
            CFRelease(cg);
            double before = nowMs();
            [view scrollWheel:event];
            @synchronized (handled) {
                [handled addObject:@[@(before - start), @(nowMs() - before), @(event.deltaY)]];
            }
            if (index == events - 1) dispatch_semaphore_signal(done);
        });
    }
    if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 300 * NSEC_PER_SEC)) != 0)
        return @{@"error": @"the burst did not finish"};
    return @{@"ok": @YES, @"events": handled, @"end_ms": @(nowMs())};
}

static NSDictionary *state(void) {
    return onMain(^id {
        NSMutableArray *out = [NSMutableArray array];
        double now = nowMs();
        for (NSView *view in views()) {
            id pix = [(id)view curDCM];
            long width = [pix pwidth], height = [pix pheight];
            float *image = [pix fImage];
            double sum = 0; long count = 0;
            if (image && width > 3 && height > 3)
                for (long y = height / 4; y < 3 * height / 4; y++)
                    for (long x = width / 4; x < 3 * width / 4; x++, count++)
                        sum += image[y * width + x];
            NSValue *key = [NSValue valueWithPointer:(__bridge void *)view];
            [out addObject:@{@"width": @(width), @"height": @(height), @"central_mean": count ? @(sum / count) : [NSNull null],
                             @"draws": drawCounts[key] ?: @0,
                             @"since_last_draw_ms": lastDraws[key] ? @(now - lastDraws[key].doubleValue) : [NSNull null],
                             @"needs_display": @(view.needsDisplay), @"hidden": @(view.isHiddenOrHasHiddenAncestor),
                             @"window_visible": @(view.window.isVisible), @"frame": screenFrame(view)}];
        }
        return @{@"now_ms": @(now), @"views": out, @"low_lod": @(mprController ? [mprController lowLOD] : NO)};
    });
}

static NSDictionary *run(NSDictionary *command) {
    NSString *action = command[@"action"];
    if ([action isEqualToString:@"ping"]) return @{@"ok": @YES};
    if ([action isEqualToString:@"open"]) return openMPR(command);
    if ([action isEqualToString:@"burst"]) return burst(command);
    if ([action isEqualToString:@"state"]) return state();
    return @{@"error": [NSString stringWithFormat:@"unknown action %@", action]};
}

__attribute__((constructor)) static void installMPRScrollBurstProbe(void) {
    NSString *folder = NSProcessInfo.processInfo.environment[@"HOROS_MPR_COMMANDS"];
    if (!folder) return;
    unsetenv("DYLD_INSERT_LIBRARIES");
    drawCounts = [NSMutableDictionary dictionary];
    lastDraws = [NSMutableDictionary dictionary];
    [NSNotificationCenter.defaultCenter addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil
                                                     queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        Method draw = class_getInstanceMethod(NSClassFromString(@"DCMView"), @selector(drawRect:));
        if (draw) originalDrawRect = method_setImplementation(draw, (IMP)countedDrawRect);
        [NSThread detachNewThreadWithBlock:^{
            for (NSInteger number = 1;; number++) {
                NSString *commandPath = [folder stringByAppendingPathComponent:[NSString stringWithFormat:@"%ld.json", (long)number]];
                while (![NSFileManager.defaultManager fileExistsAtPath:commandPath]) usleep(20 * 1000);
                @autoreleasepool {
                    NSDictionary *command = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:commandPath]
                                                                            options:0 error:NULL];
                    NSDictionary *answer;
                    @try {
                        answer = command ? run(command) : @{@"error": @"unreadable command"};
                    } @catch (NSException *exception) {
                        answer = @{@"exception": [NSString stringWithFormat:@"%@: %@", exception.name, exception.reason]};
                    }
                    NSData *data = [NSJSONSerialization dataWithJSONObject:answer options:0 error:NULL]
                        ?: [@"{\"error\": \"unserialisable answer\"}" dataUsingEncoding:NSUTF8StringEncoding];
                    NSString *partial = [folder stringByAppendingPathComponent:[NSString stringWithFormat:@".%ld.out.json", (long)number]];
                    [data writeToFile:partial atomically:NO];
                    rename(partial.fileSystemRepresentation,
                           [[folder stringByAppendingPathComponent:[NSString stringWithFormat:@"%ld.out.json", (long)number]] fileSystemRepresentation]);
                }
            }
        }];
    }];
}
