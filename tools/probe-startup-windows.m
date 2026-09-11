// Diagnostic-only probe: name the component that created each window.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-startup-windows.m \
//     -o <dir>/probe.dylib && codesign --force --sign - <dir>/probe.dylib
//
// Injected with DYLD_INSERT_LIBRARIES into the development bundle, which needs
// `com.apple.security.cs.allow-dyld-environment-variables`; `script/build_and_run.sh
// --diagnostics` builds and signs it that way. `nohup` is a platform binary and
// dyld purges DYLD_* for those, so launch from a subshell with `exec` instead.
//
// HOROS_STARTUP_WINDOWS=<seconds to watch> (default 60; 0 watches until the
// application quits). It censuses -[NSApplication windows] every second and
// prints a line for each window that appears or disappears, carrying everything
// that can name its author:
//
//   * the window's class and the bundle that class comes from - a plain NSWindow
//     from a nib reads as AppKit, so this alone identifies nothing;
//   * its window controller, delegate, content view controller and content view,
//     each with its own bundle: a window made by a plugin has at least one of
//     these in the plugin's bundle;
//   * the content view's class, which is what names AppKit's own debugging
//     windows - _NSVisualizedConstraintsView is the constraint visualizer, the
//     purple window of horosproject/horos#180, and for that one the probe also
//     reports the window it is drawn around and the constraints it found, which
//     name the view and so the component that specified them;
//   * the title, frame, level and visibility.
//
// It also lists the plugin bundles that are loaded. It changes nothing.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>

static NSString *bundleOf(Class aClass) {
    if (aClass == Nil) return @"-";
    NSBundle *bundle = [NSBundle bundleForClass:aClass];
    if (bundle == nil) return @"(none)";
    if (bundle == NSBundle.mainBundle) return @"the application";
    NSString *name = bundle.bundlePath.lastPathComponent;
    NSString *identifier = bundle.bundleIdentifier;
    return identifier.length ? [NSString stringWithFormat:@"%@ [%@]", name, identifier] : name;
}

static NSString *describe(id object, NSString *label) {
    if (object == nil) return [NSString stringWithFormat:@"%@=-", label];
    return [NSString stringWithFormat:@"%@=%@ <%@>", label,
            NSStringFromClass([object class]), bundleOf([object class])];
}

// AppKit draws its constraint visualizer in a window of its own, over the window
// whose layout it is complaining about. The view holds both: `targetWindow` is
// what it is drawn around, `constraintsToBeVisualized` names the views. Reading
// them turns "a purple window appeared" into the component that specified the
// constraints. Nothing is set, and an AppKit that no longer has these ivars
// simply reports nothing extra.
static void reportVisualizer(NSView *view) {
    NSWindow *target = [view valueForKey:@"targetWindow"];
    if (target) {
        NSLog(@"WINDOW278   visualizing %@ <%@> %@ %@ %@ title=\"%@\" frame=%@",
              NSStringFromClass(target.class), bundleOf(target.class),
              describe(target.windowController, @"controller"),
              describe(target.delegate, @"delegate"),
              describe(target.contentView, @"contentView"),
              target.title, NSStringFromRect(target.frame));
    }
    for (id constraint in [view valueForKey:@"constraintsToBeVisualized"])
        NSLog(@"WINDOW278   constraint %@", constraint);
    for (id constraint in [view valueForKey:@"constraintsNotVisualized"])
        NSLog(@"WINDOW278   not visualized %@", constraint);
}

// AppKit fills the visualizer in when it decides to complain and empties it again
// when the window is dismissed, so this is looked at far more often than the
// census - a second is long enough to miss it entirely.
static void watchVisualizers(NSMutableSet *reported) {
    for (NSWindow *window in NSApp.windows) {
        NSView *content = window.contentView;
        if (![NSStringFromClass([content class]) isEqualToString:@"_NSVisualizedConstraintsView"]) continue;
        @try {
            NSWindow *target = [content valueForKey:@"targetWindow"];
            NSSet *constraints = [content valueForKey:@"constraintsToBeVisualized"];
            if (target == nil && constraints.count == 0) continue;
            NSString *key = [NSString stringWithFormat:@"%p/%lu", target, (unsigned long)constraints.count];
            if ([reported containsObject:key]) continue;
            [reported addObject:key];
            reportVisualizer(content);
        } @catch (NSException *exception) {
            NSLog(@"WINDOW278   (AppKit no longer exposes the visualizer's contents: %@)", exception.reason);
            return;
        }
    }
}

// The visualizer is put up while the main thread is still inside whatever caused
// it - during plugin loading, say - and no timer runs then. Ordering the window
// in is the moment it is on screen with its contents still set, so take the
// report from there and leave the timer as a backstop.
static IMP originalOrderWindow;
static void hookedOrderWindow(id self, SEL _cmd, NSWindowOrderingMode place, NSInteger other) {
    ((void (*)(id, SEL, NSWindowOrderingMode, NSInteger))originalOrderWindow)(self, _cmd, place, other);
    NSWindow *window = self;
    if ([NSStringFromClass([window.contentView class]) isEqualToString:@"_NSVisualizedConstraintsView"])
        @try { reportVisualizer(window.contentView); }
        @catch (NSException *exception) { NSLog(@"WINDOW278   (%@)", exception.reason); }
}

static void census(NSMutableSet *seen) {
    NSMutableSet *now = [NSMutableSet set];
    for (NSWindow *window in NSApp.windows) {
        NSNumber *number = @(window.windowNumber);
        [now addObject:number];
        if ([seen containsObject:number]) continue;
        NSLog(@"WINDOW278 + #%ld %@ <%@> %@ %@ %@ %@ title=\"%@\" level=%ld visible=%d frame=%@",
              (long)window.windowNumber, NSStringFromClass(window.class), bundleOf(window.class),
              describe(window.windowController, @"controller"),
              describe(window.delegate, @"delegate"),
              describe(window.contentViewController, @"contentController"),
              describe(window.contentView, @"contentView"),
              window.title, (long)window.level, window.isVisible,
              NSStringFromRect(window.frame));
    }
    for (NSNumber *number in [seen copy])
        if (![now containsObject:number]) NSLog(@"WINDOW278 - #%@ closed", number);
    [seen setSet:now];
}

__attribute__((constructor)) static void install(void) {
    const char *watch = getenv("HOROS_STARTUP_WINDOWS");
    if (!watch) return;
    double seconds = atof(watch);
    if (seconds < 0) seconds = 60;

    Method order = class_getInstanceMethod(NSWindow.class, @selector(orderWindow:relativeTo:));
    if (order) originalOrderWindow = method_setImplementation(order, (IMP)hookedOrderWindow);

    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification
                                                      object:nil queue:NSOperationQueue.mainQueue
                                                  usingBlock:^(NSNotification *note) {
        NSMutableArray *plugins = [NSMutableArray array];
        for (NSBundle *bundle in [NSBundle allBundles])
            if (bundle != NSBundle.mainBundle &&
                ([bundle.bundlePath.pathExtension isEqualToString:@"horosplugin"] ||
                 [bundle.bundlePath.pathExtension isEqualToString:@"osirixplugin"] ||
                 [bundle.bundlePath.pathExtension isEqualToString:@"plugin"]))
                [plugins addObject:bundle.bundlePath.lastPathComponent];
        NSLog(@"WINDOW278 %lu plugin bundle(s) loaded: %@", (unsigned long)plugins.count,
              plugins.count ? [plugins componentsJoinedByString:@", "] : @"none");

        NSMutableSet *seen = [NSMutableSet set];
        NSMutableSet *reported = [NSMutableSet set];
        census(seen);
        watchVisualizers(reported);
        NSDate *until = seconds > 0 ? [NSDate dateWithTimeIntervalSinceNow:seconds] : NSDate.distantFuture;
        // A modal session or a tracking loop runs in its own run loop mode, and
        // a timer scheduled the usual way stops firing for as long as it lasts.
        __block NSUInteger ticks = 0;
        NSTimer *timer = [NSTimer timerWithTimeInterval:0.05 repeats:YES block:^(NSTimer *t) {
            watchVisualizers(reported);
            if (++ticks % 20 == 0) census(seen);
            if ([NSDate.date compare:until] == NSOrderedDescending) {
                NSLog(@"WINDOW278 done");
                [t invalidate];
            }
        }];
        [NSRunLoop.mainRunLoop addTimer:timer forMode:NSRunLoopCommonModes];
    }];
}
