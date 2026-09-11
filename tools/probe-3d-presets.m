// Diagnostic-only probe for #34: how long the 3D preset panel takes, per step.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-3d-presets.m \
//     -o local-validation/work/presets34/probe.dylib
//
// Load it into the isolated development bundle with DYLD_INSERT_LIBRARIES and
// HOROS_PRESET_PROBE=1, with a VR window open. It drives the panel the way the
// controls do - open, switch group, page, apply - and times each step. It reads
// no patient data and writes nothing.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>

@interface NSObject (PresetProbe)
- (void)showPresetsPanel;
- (void)selectGroupWithName:(NSString*)name;
- (void)displayPresetsForSelectedGroup;
- (void)nextPresetPage:(id)sender;
- (void)load3DSettings;
- (void)VRViewer:(id)sender;
- (BOOL)isEmpty;
@end

static double now(void) { return [NSDate timeIntervalSinceReferenceDate]; }

// The reports are of the interface freezing, so measure that directly: a
// heartbeat on the main run loop, and the largest gap between two beats. A beat
// that is late by a second is a second in which nothing could be clicked.
static double lastBeat = 0;
static double worstStall = 0;
static void beat(void) {
    double t = now();
    if (lastBeat > 0 && t - lastBeat > worstStall) worstStall = t - lastBeat;
    lastBeat = t;
}
static double takeStall(void) { double s = worstStall; worstStall = 0; lastBeat = now(); return s; }

// Drawing the nine previews is what the panel actually costs; -display makes it
// happen now instead of at the next display pass, so it can be timed.
static double drawPanel(NSWindow *panel) {
    double began = now();
    [panel display];
    return now() - began;
}

// -[NSWindow display] costs nothing when the window server has nothing to show,
// so time each preview view instead: a VRPresetPreview is a VRView, and drawing
// it is the render. Returns the total and reports the slowest.
static double drawPreviews(NSArray *previews, double *slowest) {
    double total = 0; *slowest = 0;
    for (NSView *preview in previews) {
        if ([preview respondsToSelector:@selector(isEmpty)] && [(id)preview isEmpty]) continue;
        double began = now();
        [preview setNeedsDisplay:YES];
        [preview displayIfNeeded];
        double took = now() - began;
        total += took;
        if (took > *slowest) *slowest = took;
    }
    return total;
}

static id ivarValue(id object, const char *name) {
    Ivar ivar = class_getInstanceVariable([object class], name);
    return ivar ? object_getIvar(object, ivar) : nil;
}

static long ivarLong(id object, const char *name) {
    Ivar ivar = class_getInstanceVariable([object class], name);
    if (!ivar) return -1;
    long value = 0;
    memcpy(&value, (char *)(__bridge void *)object + ivar_getOffset(ivar), sizeof(long));
    return value;
}

static void measure(id vr) {
    NSPopUpButton *groups = ivarValue(vr, "presetsGroupPopUpButton");
    NSWindow *panel = ivarValue(vr, "presetsPanel");
    NSArray *previews = ivarValue(vr, "presetPreviewArray");
    NSLog(@"PRESET34 panel=%@ groups=%lu previewSlots=%lu", panel ? @"yes" : @"no",
          (unsigned long)groups.numberOfItems, (unsigned long)previews.count);

    double began = now();
    [vr showPresetsPanel];
    NSLog(@"PRESET34 open %.3f s, panel visible=%d, groups now %lu",
          now() - began, panel.isVisible, (unsigned long)groups.numberOfItems);

    NSMutableArray *titles = [NSMutableArray array];
    for (NSMenuItem *item in groups.itemArray) [titles addObject:item.title];
    NSLog(@"PRESET34 groups: %@", [titles componentsJoinedByString:@", "]);

    NSLog(@"PRESET34 panelWindowNumber=%ld", (long)panel.windowNumber);

    // Repeatedly, because the reports are of it failing after a while, not the
    // first time.
    for (int round = 1; round <= 5; round++) {
        for (NSString *title in titles) {
            takeStall();
            began = now();
            [vr selectGroupWithName:title];
            double switched = now() - began;
            double drawn = drawPanel(panel);
            double slowest = 0;
            double previewDraw = drawPreviews(previews, &slowest);
            long pages = ivarLong(vr, "presetPageMax") + 1;
            NSUInteger filled = 0;
            for (id preview in previews)
                if ([preview respondsToSelector:@selector(isEmpty)] && ![preview isEmpty]) filled++;
            NSLog(@"PRESET34 round %d group \"%@\" switch %.3f s windowDraw %.3f s "
                  @"previews %.3f s (slowest %.3f s) stall %.3f s pages %ld filled %lu/%lu",
                  round, title, switched, drawn, previewDraw, slowest, takeStall(), pages,
                  (unsigned long)filled, (unsigned long)previews.count);
            for (long page = 1; page < pages; page++) {
                began = now();
                [vr nextPresetPage:nil];
                double pageDraw = drawPanel(panel);
                NSLog(@"PRESET34 round %d   page %ld of %ld  switch %.3f s draw %.3f s stall %.3f s",
                      round, page + 1, pages, now() - began, pageDraw, takeStall());
            }
            [vr selectGroupWithName:title];
            [panel display];
            takeStall();
            began = now();
            [vr load3DSettings];
            NSLog(@"PRESET34 round %d group \"%@\" apply %.3f s stall %.3f s panelVisible=%d",
                  round, title, now() - began, takeStall(), panel.isVisible);
            if (!panel.isVisible) [vr showPresetsPanel];
        }
    }

    // The panel has to close while it is the thing in front, and reopen.
    began = now();
    [panel close];
    NSLog(@"PRESET34 close %.3f s, visible=%d", now() - began, panel.isVisible);
    began = now();
    [vr showPresetsPanel];
    NSLog(@"PRESET34 reopen %.3f s, visible=%d", now() - began, panel.isVisible);
    double slowest = 0;
    NSLog(@"PRESET34 final previews %.3f s (slowest %.3f s); panel left open, window %ld",
          drawPreviews(previews, &slowest), slowest, (long)panel.windowNumber);
    // A group whose presets have gone while the panel is open - the last preset of
    // a group deleted from the 3D preferences, then Revert Series, which calls
    // displayPresetsForSelectedGroup. Driven from outside: remove the files, then
    // create the trigger file named by HOROS_PRESET_EMPTY_GROUP.
    const char *trigger = getenv("HOROS_PRESET_EMPTY_GROUP");
    if (trigger) {
        NSString *path = [NSString stringWithUTF8String:trigger];
        NSLog(@"PRESET34 waiting for %@ before refreshing the group", path);
        NSTimer *watch = [NSTimer timerWithTimeInterval:1.0 repeats:YES block:^(NSTimer *timer) {
            if (![NSFileManager.defaultManager fileExistsAtPath:path]) return;
            [timer invalidate];
            NSPopUpButton *groups = ivarValue(vr, "presetsGroupPopUpButton");
            NSLog(@"PRESET34 refreshing group \"%@\" with its presets removed",
                  groups.titleOfSelectedItem);
            @try {
                [vr displayPresetsForSelectedGroup];
                NSLog(@"PRESET34 survived the empty group");
            }
            @catch (NSException *e) {
                NSLog(@"PRESET34 EMPTY_GROUP_EXCEPTION %@: %@\n%@", e.name, e.reason,
                      [e.callStackSymbols componentsJoinedByString:@"\n"]);
            }
        }];
        [NSRunLoop.mainRunLoop addTimer:watch forMode:NSRunLoopCommonModes];
    }
    NSLog(@"PRESET34 done");
}

__attribute__((constructor)) static void install(void) {
    if (!getenv("HOROS_PRESET_PROBE")) return;
    if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"]) return;
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
                                                      object:nil queue:NSOperationQueue.mainQueue
                                                  usingBlock:^(NSNotification *n) {
        NSLog(@"PRESET34 probe installed");
        NSTimer *heart = [NSTimer timerWithTimeInterval:0.05 repeats:YES
                                                  block:^(NSTimer *t) { beat(); }];
        [NSRunLoop.mainRunLoop addTimer:heart forMode:NSRunLoopCommonModes];
        __block BOOL measured = NO;
        __block BOOL asked = NO;
        NSTimer *wait = [NSTimer timerWithTimeInterval:3.0 repeats:YES block:^(NSTimer *timer) {
            if (measured) { [timer invalidate]; return; }
            // No VR window yet: ask the open 2D viewer for one, once, the way its
            // toolbar does.
            BOOL haveVR = NO;
            for (NSWindow *window in [NSApp.windows copy])
                if ([NSStringFromClass([window.windowController class]) isEqualToString:@"VRController"]
                    && window.isVisible) haveVR = YES;
            if (!haveVR && !asked) {
                for (NSWindow *window in [NSApp.windows copy]) {
                    id viewer = window.windowController;
                    if (![NSStringFromClass([viewer class]) isEqualToString:@"ViewerController"]) continue;
                    if (![viewer respondsToSelector:@selector(VRViewer:)]) continue;
                    asked = YES;
                    NSLog(@"PRESET34 asking the viewer for a VR window");
                    [viewer VRViewer:nil];
                    break;
                }
                return;
            }
            for (NSWindow *window in [NSApp.windows copy]) {
                id controller = window.windowController;
                if (![NSStringFromClass([controller class]) isEqualToString:@"VRController"]) continue;
                if (!window.isVisible) continue;
                measured = YES;
                measure(controller);
                break;
            }
        }];
        [NSRunLoop.mainRunLoop addTimer:wait forMode:NSRunLoopCommonModes];
    }];
}
