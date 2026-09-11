// Diagnostic-only: opens the actual preferences controller in a private development DB.
// Set HOROS_PREFERENCES_FAILURE=1 to simulate a missing pane resource. No preferences are modified.
#import <Cocoa/Cocoa.h>
#import <PreferencePanes/PreferencePanes.h>
@interface NSObject (PreferencesProbe)
+ (id)sharedPreferencesWindowController;
+ (id)activeLocalDatabase;
- (NSString*)dataBaseDirPath;
- (void)setCurrentContext:(id)context;
- (void)setCurrentContextWithResourceName:(NSString*)name;
- (id)initWithTitle:(NSString*)title withResourceNamed:(NSString*)resource inBundle:(NSBundle*)bundle;
@end
@interface MissingProbePane:NSPreferencePane @end
@implementation MissingProbePane
- (NSView*)loadMainView { [NSException raise:@"SyntheticMissingResource" format:@"Fixture resource unavailable"]; return nil; }
@end
static id controller, badContext;
__attribute__((constructor)) static void install(void) {
 if(!getenv("HOROS_PREFERENCES_PROBE"))return;
 [[NSNotificationCenter defaultCenter] addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*n){
 dispatch_after(dispatch_time(DISPATCH_TIME_NOW,3*NSEC_PER_SEC),dispatch_get_main_queue(),^{
 if(![NSBundle.mainBundle.bundleIdentifier isEqualToString:@"org.horosproject.horos.local-development"])return;
 if(![[[NSClassFromString(@"DicomDatabase") activeLocalDatabase] dataBaseDirPath] containsString:@"/local-validation/"])return;
 controller=[NSClassFromString(@"PreferencesWindowController") sharedPreferencesWindowController];
 [controller showWindow:nil];
 if(!getenv("HOROS_PREFERENCES_FAILURE"))return;
 const char *base=getenv("HOROS_PREFERENCES_BASE_PANE");
 [controller setCurrentContextWithResourceName:base ? [NSString stringWithUTF8String:base] : @"OSILocationsPreferencePanePref"];
 NSArray *keys=@[@"AETITLE",@"AEPORT",@"TLSStoreSCPAETITLE",@"TLSStoreSCPAEPORT"];
 NSDictionary *configurationBefore=[NSUserDefaults.standardUserDefaults dictionaryWithValuesForKeys:keys];
 NSWindow *w=[controller window]; NSView *before=w.contentView;
 NSLog(@"PREF_BEFORE title=%@ size=%@ children=%lu",w.title,NSStringFromSize(before.frame.size),(unsigned long)before.subviews.count);
 badContext=[[NSClassFromString(@"PreferencesWindowContext") alloc] initWithTitle:@"Missing synthetic pane" withResourceNamed:@"MissingProbePane" inBundle:NSBundle.mainBundle];
 @try { [controller setCurrentContext:badContext]; } @catch(NSException*e){ NSLog(@"PREF_THROW %@",e.name); }
 NSLog(@"PREF_CONFIGURATION_PRESERVED %d",[configurationBefore isEqual:[NSUserDefaults.standardUserDefaults dictionaryWithValuesForKeys:keys]]);
 NSLog(@"PREF_AFTER sameView=%d size=%@ children=%lu",before==w.contentView,NSStringFromSize(w.contentView.frame.size),(unsigned long)w.contentView.subviews.count);
 }); }];
}
