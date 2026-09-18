// Surface Rendering's iso-surfaces from inside the development app (#636), injected
// with DYLD_INSERT_LIBRARIES and driven by numbered command files.
//
//   HOROS_SR_COMMANDS  a folder: <n>.json is run for n = 1, 2, ... in order, and
//                      answered in <n>.out.json (written whole, then renamed)
//
//   {"action": "ping"}
//   {"action": "series"}
//       every series of the database: its SeriesInstanceUID and number of images
//   {"action": "open", "main": "<SeriesInstanceUID>", "fusion": "<SeriesInstanceUID>"}
//       both series opened as the browser opens them; once loaded, the fusion
//       series is fused onto the main one (-ActivateBlending:, planes parallel)
//       and the main viewer's Surface Rendering window is opened with it
//       (-openSRViewer, as -SRViewer: does)
//   {"action": "export", "target": "main"|"fusion", "surfaces": [0 and/or 1],
//    "decimate": bool, "smooth": bool, "first": iso, "second": iso, "path": "....stl",
//    "keep": "recolour"|"reiso"|"invalidate" (optional)}
//       every surface actor removed, the controller's settings set as the settings
//       sheet sets them (resolution 0.5, reduction 0.5, 20 iterations: the defaults),
//       the surfaces rendered as -ApplySettings: renders them (-renderSurfaces or,
//       for the fusion, -renderFusionSurfaces), then File > Export > STL
//       (-[SRView export3DFileFormat:], its save panel answered with "path").
//       With "keep" (#616) the surfaces are rendered twice, with the change below
//       between the renders, and the second one is timed (render_ms) and exported.
//   {"action": "measure", "repetitions": n, "reference": bool,
//    "scenarios": [{"name", "target", "decimate", "smooth", "first", "second",
//                   "reference_path": "surfaces"|"fusion-surfaces"|null}]}
//       for tools/measure-native-sr-surfaces.py: before each call every actor is
//       removed, then the call is timed on the main thread: <name>_ms (wall) and
//       <name>_cpu_ms (main thread CPU). The first repetition is a warm-up and is
//       not reported; the order of the scenarios rotates by repetition. With
//       "reference" true, a scenario with a reference path is rendered by that
//       path instead: "surfaces" calls -[SRView changeActor:...] for each surface
//       with the options the sheet asked for, as -renderSurfaces does once #636 is
//       fixed; "fusion-surfaces" makes the same calls without the wait window, as
//       -renderFusionSurfaces renders, on the main volume (the fusion series is an
//       identical copy, so the filters do the same work). Each is the functional
//       reference for a revision whose own call was wrong or crashed.
//       A scenario with "keep" (#616) is timed on surfaces already rendered with its options
//       (untimed, in the first colours): "recolour" changes only the colours and the
//       transparencies before the timed render, "reiso" only the first surface's iso value
//       (by 25), as a second OK of the settings sheet does; "invalidate" changes the colours
//       after posting the notification a viewer posts once it has changed the voxels.
//
//   xcrun clang -dynamiclib -fobjc-arc -framework Cocoa tools/probe-sr-surfaces.m -o probe-sr-surfaces.dylib
#import <Cocoa/Cocoa.h>
#include <mach/mach_time.h>
#include <objc/message.h>
#include <objc/runtime.h>
#include <time.h>

@interface NSObject (SRSurfacesProbe)
+ (id)activeLocalDatabase;
+ (id)currentBrowser;
- (NSArray *)objectsForEntity:(id)entity;
- (id)entityForName:(NSString *)name;
- (id)loadSeries:(id)series :(id)viewer :(BOOL)firstViewer keyImagesOnly:(BOOL)keyImages;
- (BOOL)isEverythingLoaded;
- (void)ActivateBlending:(id)viewer;
- (id)blendingController;
- (NSMutableArray *)pixList;
- (id)openSRViewer;
- (id)view;
- (void)renderSurfaces;
- (void)renderFusionSurfaces;
- (void)deleteActor:(long)actor;
- (void)BdeleteActor:(long)actor;
- (void)changeActor:(long)actor :(float)resolution :(float)transparency :(float)r :(float)g :(float)b :(float)isocontour
                   :(BOOL)useDecimate :(float)decimateVal :(BOOL)useSmooth :(long)smoothVal;
- (IBAction)export3DFileFormat:(id)sender;
- (id)init:(NSString *)message;
- (void)start;
- (void)end;
@end

static NSString *exportPath = nil;
static id srController = nil;

static double milliseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1e6;
}

static double threadCPUms(void) {
    struct timespec now;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now);
    return now.tv_sec * 1e3 + now.tv_nsec / 1e6;
}

static id onMain(id (^block)(void)) {
    __block id result = nil;
    if ([NSThread isMainThread]) return block();
    dispatch_sync(dispatch_get_main_queue(), ^{ result = block(); });
    return result;
}

// The export's save panel is never shown: it answers OK at once with exportPath.
static void beginSavePanel(id panel, SEL selector, void (^handler)(NSModalResponse)) { handler(NSModalResponseOK); }
static NSURL *savePanelURL(id panel, SEL selector) { return exportPath ? [NSURL fileURLWithPath:exportPath] : nil; }

static NSDictionary *seriesList(void) {
    return onMain(^id {
        id database = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
        NSMutableArray *list = [NSMutableArray array];
        for (id series in [database objectsForEntity:[database entityForName:@"Series"]])
            [list addObject:@{@"uid": [series valueForKey:@"seriesDICOMUID"] ?: @"",
                              @"images": @([[series valueForKey:@"images"] count])}];
        return @{@"series": list};
    });
}

static id viewerFor(NSString *uid, BOOL first) {
    return onMain(^id {
        id database = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
        for (id series in [database objectsForEntity:[database entityForName:@"Series"]])
            if ([[series valueForKey:@"seriesDICOMUID"] isEqualToString:uid])
                return [[NSClassFromString(@"BrowserController") currentBrowser] loadSeries:series :nil :first keyImagesOnly:NO];
        return nil;
    });
}

static BOOL waitLoaded(id viewer) {
    for (int wait = 0; wait < 1200; wait++) {
        if ([onMain(^id { return @([viewer isEverythingLoaded]); }) boolValue]) return YES;
        usleep(50 * 1000);
    }
    return NO;
}

static NSDictionary *openViewers(NSDictionary *command) {
    id main = viewerFor(command[@"main"], YES);
    if (!main) return @{@"error": @"no main series"};
    if (!waitLoaded(main)) return @{@"error": @"the main series did not load"};
    id fusion = viewerFor(command[@"fusion"], NO);
    if (!fusion) return @{@"error": @"no fusion series"};
    if (!waitLoaded(fusion)) return @{@"error": @"the fusion series did not load"};
    usleep(300 * 1000);
    return onMain(^id {
        [main ActivateBlending:fusion];
        if ([main blendingController] != fusion) return @{@"error": @"the fusion was not activated"};
        srController = [main openSRViewer];
        if (!srController) return @{@"error": @"no Surface Rendering window"};
        [srController showWindow:nil];
        [[srController window] makeKeyAndOrderFront:nil];
        return @{@"ok": @YES, @"fused": @YES};
    });
}

static void removeActors(id view) {
    for (long actor = 0; actor < 2; actor++) {
        [view deleteActor:actor];
        [view BdeleteActor:actor];
    }
}

// What the settings sheet sets before -ApplySettings: renders.
static void applyOptions(NSDictionary *options) {
    NSArray *surfaces = options[@"surfaces"] ?: @[@0, @1];
    [srController setValue:@0.5f forKey:@"resolution"];
    [srController setValue:@0.5f forKey:@"decimate"];
    [srController setValue:@20 forKey:@"smooth"];
    [srController setValue:@1.0f forKey:@"firstTransparency"];
    [srController setValue:@1.0f forKey:@"secondTransparency"];
    [srController setValue:options[@"decimate"] forKey:@"shouldDecimate"];
    [srController setValue:options[@"smooth"] forKey:@"shouldSmooth"];
    [srController setValue:options[@"first"] forKey:@"firstSurface"];
    [srController setValue:options[@"second"] forKey:@"secondSurface"];
    [srController setValue:@([surfaces containsObject:@0]) forKey:@"useFirstSurface"];
    [srController setValue:@([surfaces containsObject:@1]) forKey:@"useSecondSurface"];
}

// The colours and transparencies the sheet sets: the first pair, or the other one.
static void setColours(BOOL other) {
    [srController setValue:(other ? [NSColor colorWithCalibratedRed:0.9 green:0.3 blue:0.2 alpha:1] : [NSColor colorWithCalibratedRed:0.95 green:0.9 blue:0.8 alpha:1]) forKey:@"firstColor"];
    [srController setValue:(other ? [NSColor colorWithCalibratedRed:0.2 green:0.4 blue:0.9 alpha:1] : [NSColor colorWithCalibratedRed:0.8 green:0.2 blue:0.2 alpha:1]) forKey:@"secondColor"];
    [srController setValue:@(other ? 0.6f : 1.0f) forKey:@"firstTransparency"];
    [srController setValue:@(other ? 0.4f : 1.0f) forKey:@"secondTransparency"];
}

// #616: what a second OK changes on surfaces already rendered.
static void change(NSDictionary *options, NSString *keep) {
    if ([keep isEqual:@"recolour"]) setColours(YES);
    if ([keep isEqual:@"reiso"])
        [srController setValue:@([options[@"first"] floatValue] + 25) forKey:@"firstSurface"];
    if ([keep isEqual:@"invalidate"]) {
        // The voxels the surfaces were built from: the main series', or the fused series'.
        id viewer = [options[@"target"] isEqual:@"fusion"] ? [srController blendingController] : nil;
        NSMutableArray *voxels = viewer ? [viewer pixList] : [srController valueForKey:@"pixList"];
        [NSNotificationCenter.defaultCenter postNotificationName:@"updateVolumeData" object:voxels userInfo:nil];
        setColours(YES);
    }
}

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
static void render(NSDictionary *options, BOOL reference) {
    id view = [srController view];
    NSString *path = reference ? options[@"reference_path"] : nil;
    if ([path isEqual:@"surfaces"] || [path isEqual:@"fusion-surfaces"]) {
        // -renderSurfaces as it reads once the second surface takes the smoothing option.
        BOOL wait = [path isEqual:@"surfaces"];
        id window = wait ? [[NSClassFromString(@"WaitRendering") alloc] init:NSLocalizedString(@"Preparing 3D Iso Surface...", nil)] : nil;
        [window start];
        BOOL decimate = [options[@"decimate"] boolValue], smooth = [options[@"smooth"] boolValue];
        NSColor *first = [[srController valueForKey:@"firstColor"] colorUsingColorSpaceName:NSCalibratedRGBColorSpace];
        NSColor *second = [[srController valueForKey:@"secondColor"] colorUsingColorSpaceName:NSCalibratedRGBColorSpace];
        [view changeActor:0 :0.5 :1.0 :first.redComponent :first.greenComponent :first.blueComponent
                         :[options[@"first"] floatValue] :decimate :0.5 :smooth :20];
        [view changeActor:1 :0.5 :1.0 :second.redComponent :second.greenComponent :second.blueComponent
                         :[options[@"second"] floatValue] :decimate :0.5 :smooth :20];
        [window end];
        [window close];
        return;
    }
    if ([options[@"target"] isEqual:@"fusion"]) {
        [srController setValue:@YES forKey:@"shouldRenderFusion"];
        [srController renderFusionSurfaces];
    } else {
        [srController renderSurfaces];
    }
}
#pragma clang diagnostic pop

static NSDictionary *exportSurfaces(NSDictionary *command) {
    if (!srController) return @{@"error": @"no Surface Rendering window"};
    return onMain(^id {
        id view = [srController view];
        removeActors(view);
        applyOptions(command);
        NSString *keep = command[@"keep"];
        if (keep) {
            setColours(NO);
            render(command, NO);
            change(command, keep);
        }
        uint64_t start = mach_absolute_time();
        render(command, NO);
        double renderMs = milliseconds(start, mach_absolute_time());
        exportPath = command[@"path"];
        [[NSFileManager defaultManager] removeItemAtPath:exportPath error:NULL];
        NSMenuItem *stl = [[NSMenuItem alloc] initWithTitle:@"STL" action:NULL keyEquivalent:@""];
        stl.tag = 5;
        [view export3DFileFormat:stl];
        exportPath = nil;
        NSNumber *bytes = [[NSFileManager defaultManager] attributesOfItemAtPath:command[@"path"] error:NULL][NSFileSize];
        return @{@"ok": @YES, @"render_ms": @(renderMs), @"bytes": bytes ?: @0};
    });
}

static NSDictionary *measure(NSDictionary *command) {
    if (!srController) return @{@"error": @"no Surface Rendering window"};
    NSArray *scenarios = command[@"scenarios"];
    NSInteger repetitions = [command[@"repetitions"] integerValue];
    BOOL reference = [command[@"reference"] boolValue];
    NSMutableDictionary *metrics = [NSMutableDictionary dictionary];
    for (NSInteger repetition = 0; repetition <= repetitions; repetition++) {
        for (NSUInteger index = 0; index < scenarios.count; index++) {
            NSDictionary *scenario = scenarios[(index + repetition) % scenarios.count];
            NSArray *timing = onMain(^id {
                id view = [srController view];
                removeActors(view);
                applyOptions(scenario);
                NSString *keep = scenario[@"keep"];
                if (keep) {
                    setColours(NO);
                    render(scenario, reference);
                    change(scenario, keep);
                }
                double cpu = threadCPUms();
                uint64_t start = mach_absolute_time();
                render(scenario, reference);
                uint64_t end = mach_absolute_time();
                return @[@(milliseconds(start, end)), @(threadCPUms() - cpu)];
            });
            if (repetition == 0) continue;
            NSString *wall = [scenario[@"name"] stringByAppendingString:@"_ms"];
            NSString *cpu = [scenario[@"name"] stringByAppendingString:@"_cpu_ms"];
            if (!metrics[wall]) metrics[wall] = [NSMutableArray array];
            if (!metrics[cpu]) metrics[cpu] = [NSMutableArray array];
            [metrics[wall] addObject:timing[0]];
            [metrics[cpu] addObject:timing[1]];
        }
    }
    onMain(^id { removeActors([srController view]); return nil; });
    return metrics;
}

static NSDictionary *run(NSDictionary *command) {
    NSString *action = command[@"action"];
    if ([action isEqualToString:@"ping"]) return @{@"ok": @YES};
    if ([action isEqualToString:@"series"]) return seriesList();
    if ([action isEqualToString:@"open"]) return openViewers(command);
    if ([action isEqualToString:@"export"]) return exportSurfaces(command);
    if ([action isEqualToString:@"measure"]) return measure(command);
    return @{@"error": [NSString stringWithFormat:@"unknown action %@", action]};
}

__attribute__((constructor)) static void installSRSurfacesProbe(void) {
    NSString *folder = NSProcessInfo.processInfo.environment[@"HOROS_SR_COMMANDS"];
    if (!folder) return;
    unsetenv("DYLD_INSERT_LIBRARIES");
    method_setImplementation(class_getInstanceMethod(NSSavePanel.class, @selector(beginWithCompletionHandler:)),
                             (IMP)beginSavePanel);
    method_setImplementation(class_getInstanceMethod(NSSavePanel.class, @selector(URL)), (IMP)savePanelURL);
    [NSNotificationCenter.defaultCenter addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil
                                                     queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        [NSThread detachNewThreadWithBlock:^{
            for (NSInteger number = 1;; number++) {
                NSString *commandPath = [folder stringByAppendingPathComponent:[NSString stringWithFormat:@"%ld.json", (long)number]];
                while (![NSFileManager.defaultManager fileExistsAtPath:commandPath]) usleep(50 * 1000);
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
