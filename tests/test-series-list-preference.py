#!/usr/bin/env python3
"""Run the preference observer and application transition with controlled peers."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
app = (root/'Horos/Sources/AppController.m').read_bytes().decode('latin1')
start = app.index('        BOOL seriesListModeChanged =')
transition = app[start:app.index('        if( [[previousDefaults valueForKey: @"DisplayDICOMOverlays"]', start)]
pane = (root/'Preference Panes/OSIViewerPreferencePane/OSIViewerPreferencePanePref.m').read_bytes().decode('latin1')
start = pane.index('    if( [keyPath isEqualToString: @"values.UseFloatingThumbnailsList"])')
observer = pane[start:pane.index('\n}\n', start)]
driver = r'''
#import <Foundation/Foundation.h>
#define check(c) do { if (!(c)) { fprintf(stderr, "FAIL: %s\n", #c); exit(1); } } while (0)
#define MAXSCREENS 3
static int updateDepth, closes, layouts, tiles, redraws, attaches, keyChanges;
static NSMutableArray *events;
void NSDisableScreenUpdates(void) { updateDepth++; }
void NSEnableScreenUpdates(void) { updateDepth--; }
@interface NSWindow : NSObject
@property BOOL isVisible;
- (void)makeKeyAndOrderFront:(id)sender;
@end
@interface App : NSObject
@property NSWindow *keyWindow;
@end
@implementation App
@end
static App *NSApp;
@implementation NSWindow
- (void)makeKeyAndOrderFront:(id)sender { NSApp.keyWindow = self; keyChanges++; }
@end
@interface NSScreen : NSObject
+ (NSArray *)screens;
@end
@implementation NSScreen
+ (NSArray *)screens { return @[@0, @1]; }
@end
@interface Panel : NSObject
@property BOOL borrowed;
- (void)prepareForScreenReconfiguration;
@end
@implementation Panel
- (void)prepareForScreenReconfiguration { self.borrowed = NO; [events addObject:@"detach"]; }
@end
static Panel *thumbnailsListPanel[MAXSCREENS];
@interface ViewerController : NSObject
@property NSWindow *window;
@property int index;
+ (NSArray *)get2DViewers;
+ (NSArray *)getDisplayed2DViewers;
+ (id)frontMostDisplayed2DViewerForScreen:(id)screen;
+ (void)closeAllWindows;
- (void)updateSeriesListMode;
- (void)setMatrixVisible:(BOOL)visible;
- (void)redrawToolbar;
@end
static NSArray *viewers;
@implementation ViewerController
+ (NSArray *)get2DViewers { return viewers; }
+ (NSArray *)getDisplayed2DViewers { return viewers; }
+ (id)frontMostDisplayed2DViewerForScreen:(id)screen { return viewers[[screen intValue]]; }
+ (void)closeAllWindows { closes++; }
- (void)updateSeriesListMode {
    for (int i=0; i<MAXSCREENS; i++) check(!thumbnailsListPanel[i].borrowed);
    layouts++; [events addObject:@"layout"];
}
- (void)setMatrixVisible:(BOOL)visible { check(visible); }
- (void)redrawToolbar {
    check(tiles > 0 && NSApp.keyWindow == self.window);
    redraws++; thumbnailsListPanel[self.index].borrowed = YES; attaches++;
}
@end
@interface AppController : NSObject
+ (id)sharedAppController;
- (void)tileWindows:(id)sender;
- (void)transitionFrom:(NSDictionary *)previousDefaults;
- (void)preferenceChanged;
@end
@implementation AppController
+ (id)sharedAppController { static id app; if (!app) app=[self new]; return app; }
- (void)tileWindows:(id)sender {
    tiles++;
    // Actual tiling releases panel attachments; each screen needs a new owner.
    for (int i=0; i<MAXSCREENS; i++) thumbnailsListPanel[i].borrowed=NO;
}
- (void)transitionFrom:(NSDictionary *)previousDefaults {
    NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
TRANSITION
}
- (void)preferenceChanged {
    NSString *keyPath = @"values.UseFloatingThumbnailsList";
OBSERVER
}
@end
int main(void) { @autoreleasepool {
    NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
    [defaults setVolatileDomain:@{@"UseFloatingThumbnailsList":@NO, @"SeriesListVisible":@YES}
                       forName:NSArgumentDomain];
    events = [NSMutableArray new]; NSApp = [App new];
    NSWindow *preferences = [NSWindow new]; preferences.isVisible = YES; NSApp.keyWindow = preferences;
    ViewerController *a=[ViewerController new], *b=[ViewerController new];
    a.window=[NSWindow new]; b.window=[NSWindow new]; b.index=1; viewers=@[a,b];
    for (int i=0; i<MAXSCREENS; i++) thumbnailsListPanel[i]=[Panel new];
    AppController *app=AppController.sharedAppController;
    [app preferenceChanged]; check(closes==0 && [defaults boolForKey:@"SeriesListVisible"]);
    [app transitionFrom:@{@"UseFloatingThumbnailsList":@NO,@"SeriesListVisible":@YES}];
    check(layouts==0 && tiles==0 && keyChanges==0);
    for (int cycle=0; cycle<3; cycle++) {
        [defaults setVolatileDomain:@{@"UseFloatingThumbnailsList":@YES,@"SeriesListVisible":@YES} forName:NSArgumentDomain];
        [events removeAllObjects];
        [app transitionFrom:@{@"UseFloatingThumbnailsList":@NO,@"SeriesListVisible":@YES}];
        check(([[events subarrayWithRange:NSMakeRange(0,3)] isEqual:@[@"detach",@"detach",@"detach"]]));
        check(thumbnailsListPanel[0].borrowed && thumbnailsListPanel[1].borrowed);
        check(NSApp.keyWindow == preferences && closes==0 && updateDepth==0);
        [defaults setVolatileDomain:@{@"UseFloatingThumbnailsList":@NO,@"SeriesListVisible":@YES} forName:NSArgumentDomain];
        [app transitionFrom:@{@"UseFloatingThumbnailsList":@YES,@"SeriesListVisible":@YES}];
        check(!thumbnailsListPanel[0].borrowed && !thumbnailsListPanel[1].borrowed);
        check(NSApp.keyWindow == preferences && closes==0 && updateDepth==0);
    }
    check(layouts==12 && tiles==6 && redraws==6 && attaches==6 && viewers.count==2);
    puts("PASS: no viewer closes, detach before layout, two-screen reattachment after tiling, focus restoration and unchanged-mode no-op");
}}
'''.replace('TRANSITION', transition).replace('OBSERVER', observer)
with tempfile.TemporaryDirectory(prefix='horos-series-list-preference-') as folder:
    folder = Path(folder)
    (folder/'test.m').write_text(driver)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'Foundation',
                    str(folder/'test.m'), '-o', str(folder/'test')], check=True)
    subprocess.run([str(folder/'test')], check=True)
