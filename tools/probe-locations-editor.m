// Diagnostic-only: expose the real Locations pane for UI validation in a private DB.
// Does not seed, edit, or restore preferences; use only synthetic test nodes.
#import <Cocoa/Cocoa.h>
#import <PreferencePanes/PreferencePanes.h>
@interface NSObject (LocationsEditorProbe)
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
- (id)initWithBundle:(NSBundle*)bundle;
- (void)willSelect;
@end
static id pane;
static NSWindow *window;
__attribute__((constructor)) static void install(void) {
    if (!getenv("HOROS_LOCATIONS_EDITOR_PROBE")) return;
    [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3*NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            if (![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"]) return;
            id db = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
            if (![[db dataBaseDirPath] containsString:@"/local-validation/"]) return;
            pane = [[NSClassFromString(@"OSILocationsPreferencePanePref") alloc] initWithBundle:NSBundle.mainBundle];
            NSView *view = [pane mainView];
            window = [[NSWindow alloc] initWithContentRect:view.frame styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable backing:NSBackingStoreBuffered defer:NO];
            window.title = @"Locations synthetic validation #176";
            window.contentView = view;
            [window makeKeyAndOrderFront:nil];
            [pane willSelect];
            NSLog(@"LOCATIONS_EDITOR_READY");
        });
    }];
}
