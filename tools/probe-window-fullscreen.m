// Diagnostic-only probe for #360: what every window of the running application
// declares about native full screen. Reports and changes nothing.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-window-fullscreen.m \
//     -o local-validation/work/fullscreen360/probe.dylib
//
// Load it into the isolated development bundle with DYLD_INSERT_LIBRARIES and
// HOROS_WINDOW_FULLSCREEN_PROBE=1. It logs one line per window, every few
// seconds, so windows opened during the session are covered too.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>

@interface NSObject (WindowFullScreenProbeActions)
- (void)fullScreenMenu:(id)sender;
- (BOOL)FullScreenON;
@end

@interface NSObject (WindowFullScreenProbeOwners)
+ (id)currentBrowser;
+ (id)sharedAppController;
- (id)initAutoQuery:(BOOL)value;
@end

@interface NSWindow (WindowFullScreenProbe)
- (BOOL)showsFullScreenButton;      // private AppKit; read here, never called for effect
- (BOOL)HOROS_showsFullScreenButton; // the replacement AppController installs
@end

static NSString *behaviourText(NSWindowCollectionBehavior behaviour) {
    NSMutableArray *names = [NSMutableArray array];
    if (behaviour & NSWindowCollectionBehaviorFullScreenPrimary) [names addObject:@"Primary"];
    if (behaviour & NSWindowCollectionBehaviorFullScreenAuxiliary) [names addObject:@"Auxiliary"];
    if (behaviour & NSWindowCollectionBehaviorFullScreenNone) [names addObject:@"None"];
    if (behaviour & NSWindowCollectionBehaviorFullScreenAllowsTiling) [names addObject:@"AllowsTiling"];
    if (behaviour & NSWindowCollectionBehaviorFullScreenDisallowsTiling) [names addObject:@"DisallowsTiling"];
    if (names.count == 0) [names addObject:@"-"];
    return [names componentsJoinedByString:@"+"];
}

// Does AppKit offer native full screen for a given collection behaviour? Asked of
// AppKit rather than assumed: an off-screen window is built with the behaviour and
// the Enter Full Screen menu item is validated against it. Nothing is shown.
static void experiment(void) {
    struct { const char *name; NSWindowCollectionBehavior behaviour; } cases[] = {
        {"default (0)", 0},
        {"FullScreenPrimary", NSWindowCollectionBehaviorFullScreenPrimary},
        {"FullScreenAuxiliary", NSWindowCollectionBehaviorFullScreenAuxiliary},
        {"FullScreenNone", NSWindowCollectionBehaviorFullScreenNone},
    };
    NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:@"Enter Full Screen"
                                                  action:@selector(toggleFullScreen:) keyEquivalent:@""];
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        NSWindow *scratch = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 400, 300)
            styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable|NSWindowStyleMaskResizable
              backing:NSBackingStoreBuffered defer:YES];
        scratch.collectionBehavior = cases[i].behaviour;
        scratch.title = @"FS360 scratch";
        BOOL valid = [scratch respondsToSelector:@selector(validateMenuItem:)]
                   ? [scratch validateMenuItem:item] : NO;
        id fullScreenButton = [scratch respondsToSelector:@selector(accessibilityFullScreenButton)]
                            ? [scratch accessibilityFullScreenButton] : nil;
        NSLog(@"FS360_EXPERIMENT behaviour=%s offersFullScreen=%d showsFullScreenButton=%d "
              @"accessibilityFullScreenButton=%@",
              cases[i].name, valid,
              [scratch respondsToSelector:@selector(showsFullScreenButton)]
                  ? [scratch showsFullScreenButton] : -1,
              fullScreenButton ? @"present" : @"nil");
    }
}

static void report(void) {
    NSLog(@"FS360 --- %lu window(s) ---", (unsigned long)NSApp.windows.count);
    for (NSWindow *window in NSApp.windows) {
        if ([window.title isEqualToString:@"FS360 scratch"]) continue;
        NSString *owner = NSStringFromClass([window.windowController class] ?: [NSNull class]);
        if (window.windowController == nil) {
            // A nib window held by an outlet has no window controller, so name it
            // by the outlet that holds it - otherwise the census cannot say which
            // window of the application this is.
            NSArray *holders = @[NSClassFromString(@"BrowserController") ?
                                     [NSClassFromString(@"BrowserController") currentBrowser] : nil,
                                 NSClassFromString(@"AppController") ?
                                     [NSClassFromString(@"AppController") sharedAppController] : nil];
            for (id holder in holders) {
                if (holder == nil || holder == (id)[NSNull null]) continue;
                unsigned int count = 0;
                Ivar *ivars = class_copyIvarList([holder class], &count);
                for (unsigned int j = 0; j < count; j++) {
                    const char *type = ivar_getTypeEncoding(ivars[j]);
                    if (type == NULL || type[0] != '@') continue;
                    id value = object_getIvar(holder, ivars[j]);
                    if (value == window) {
                        owner = [NSString stringWithFormat:@"%@.%s", NSStringFromClass([holder class]),
                                 ivar_getName(ivars[j])];
                        break;
                    }
                }
                if (ivars) free(ivars);
                if (![owner isEqualToString:@"NSNull"]) break;
            }
        }
        BOOL zoomButton = [window standardWindowButton:NSWindowZoomButton] != nil;
        BOOL shows = [window respondsToSelector:@selector(showsFullScreenButton)]
                   ? [window showsFullScreenButton] : NO;
        id axButton = [window respondsToSelector:@selector(accessibilityFullScreenButton)]
                    ? [window accessibilityFullScreenButton] : nil;
        NSLog(@"FS360 class=%@ controller=%@ title=\"%@\" behaviour=0x%lx(%@) zoomButton=%d "
              @"showsFullScreenButton=%d fullScreenButton=%@ titled=%d resizable=%d "
              @"inFullScreen=%d visible=%d",
              NSStringFromClass(window.class), owner, window.title,
              (unsigned long)window.collectionBehavior, behaviourText(window.collectionBehavior),
              zoomButton, shows, axButton ? @"present" : @"nil",
              (window.styleMask & NSWindowStyleMaskTitled) != 0,
              (window.styleMask & NSWindowStyleMaskResizable) != 0,
              (window.styleMask & NSWindowStyleMaskFullScreen) != 0, window.isVisible);
    }
}

__attribute__((constructor)) static void install(void) {
    if (!getenv("HOROS_WINDOW_FULLSCREEN_PROBE")) return;
    if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"]) return;
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
                                                      object:nil queue:NSOperationQueue.mainQueue
                                                  usingBlock:^(NSNotification *n) {
        NSLog(@"FS360 probe installed; NSWindow responds to showsFullScreenButton: %d",
              [NSWindow instancesRespondToSelector:@selector(showsFullScreenButton)]);
        experiment();
        // A default-mode timer stops firing while a window is tracking or modal,
        // which is exactly when the interesting windows appear. Common modes.
        NSTimer *census = [NSTimer timerWithTimeInterval:6.0 repeats:YES
                                                   block:^(NSTimer *t) { report(); }];
        [NSRunLoop.mainRunLoop addTimer:census forMode:NSRunLoopCommonModes];
        // Undo the swizzle AppController installs, in this process only, and ask
        // the same questions again: that is the before and after, side by side.
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 8 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            NSLog(@"FS360 --- as this build runs ---");
            experiment();
            report();
            Method original = class_getInstanceMethod(NSWindow.class, @selector(showsFullScreenButton));
            Method replacement = class_getInstanceMethod(NSWindow.class, @selector(HOROS_showsFullScreenButton));
            if (original && replacement) {
                method_exchangeImplementations(original, replacement);
                NSLog(@"FS360 --- swizzle undone in this process ---");
                experiment();
                report();
            } else {
                NSLog(@"FS360 --- no replacement to undo: the build carries no swizzle ---");
            }
            // Open the families that only exist once a series is on screen, the way
            // the toolbar does, and report them too.
            if (getenv("HOROS_WINDOW_FULLSCREEN_OPEN") || getenv("HOROS_WINDOW_FULLSCREEN_TOGGLE")) {
                __block BOOL opened = NO;
                [NSTimer scheduledTimerWithTimeInterval:3.0 repeats:YES block:^(NSTimer *timer) {
                    if (opened) { [timer invalidate]; return; }
                    for (NSWindow *window in [NSApp.windows copy]) {
                        id controller = window.windowController;
                        if (![NSStringFromClass([controller class]) isEqualToString:@"ViewerController"]) continue;
                        for (NSString *action in getenv("HOROS_WINDOW_FULLSCREEN_OPEN")
                                                  ? @[@"mprViewer:", @"VRViewer:"] : @[]) {
                            SEL selector = NSSelectorFromString(action);
                            if ([controller respondsToSelector:selector]) {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"
                                [controller performSelector:selector withObject:nil];
#pragma clang diagnostic pop
                                NSLog(@"FS360 asked the viewer for %@", action);
                            }
                        }
                        // And the Query/Retrieve window, which is the other family
                        // that asks for a full-screen Space of its own.
                        Class query = getenv("HOROS_WINDOW_FULLSCREEN_OPEN")
                                    ? NSClassFromString(@"QueryController") : nil;
                        if (query && [query instancesRespondToSelector:@selector(initAutoQuery:)]) {
                            (void)[[query alloc] initAutoQuery:NO];
                            NSLog(@"FS360 opened the Query/Retrieve window");
                        }
                        // Horos's own full screen has to keep working: it is the
                        // one the viewer and the 3D windows actually use. In and
                        // straight back out, counting the borderless window.
                        if (getenv("HOROS_WINDOW_FULLSCREEN_TOGGLE")
                            && [controller respondsToSelector:@selector(fullScreenMenu:)]) {
                            NSUInteger before = NSApp.windows.count;
                            [controller fullScreenMenu:nil];
                            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC),
                                           dispatch_get_main_queue(), ^{
                                NSUInteger during = 0;
                                NSWindow *borderless = nil;
                                for (NSWindow *w in NSApp.windows)
                                    if (w.isVisible && (w.styleMask & NSWindowStyleMaskTitled) == 0
                                        && NSEqualSizes(w.frame.size, NSScreen.mainScreen.frame.size)) {
                                        borderless = w; during++;
                                    }
                                NSLog(@"FS360_OWN_FULLSCREEN entered=%d borderlessFullSizeWindows=%lu "
                                      @"windowsBefore=%lu now=%lu",
                                      borderless != nil, (unsigned long)during,
                                      (unsigned long)before, (unsigned long)NSApp.windows.count);
                                [controller fullScreenMenu:nil];
                                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC),
                                               dispatch_get_main_queue(), ^{
                                    NSUInteger after = 0;
                                    for (NSWindow *w in NSApp.windows)
                                        if (w.isVisible && (w.styleMask & NSWindowStyleMaskTitled) == 0
                                            && NSEqualSizes(w.frame.size, NSScreen.mainScreen.frame.size)) after++;
                                    NSLog(@"FS360_OWN_FULLSCREEN left=%d borderlessFullSizeWindows=%lu",
                                          after == 0, (unsigned long)after);
                                });
                            });
                        }
                        opened = YES;
                        break;
                    }
                }];
            }
        });
    }];
}
