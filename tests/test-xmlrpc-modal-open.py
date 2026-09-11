#!/usr/bin/env python3
"""Execute the production open method against a real run loop and fake UI/model.

No windows are created. A modal-loop marker lets us assert that an accepted
request does not close/activate/resolve/open anything until the operator leaves
the modal state, including a nested default loop. Optionally test an old ref.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (subprocess.check_output(['git', 'show', sys.argv[1]+':Horos/Sources/XMLRPCMethods.mm']).decode('latin1')
          if len(sys.argv) > 1 else (root/'Horos/Sources/XMLRPCMethods.mm').read_bytes().decode('latin1'))
start = source.index('-(void)_onMainThreadOpenObjectsWithIDs:')
method = source[start:source.index('-(void)_onMainThreadSelectObjectsWithIDs:', start)]
driver = r'''
#import <AppKit/AppKit.h>
#define check(c) do { if (!(c)) { fprintf(stderr, "failed: %s\n", #c); exit(1); } } while (0)
#define NSManagedObject NSObject
static int closes, opens, activations, resolutions, refusals, modalReads;
@interface AppProbe : NSObject
@property id activeModal;
- (id)modalWindow;
- (void)activateIgnoringOtherApps:(BOOL)value;
@end
@implementation AppProbe
- (id)modalWindow { check(NSThread.isMainThread); modalReads++; return self.activeModal; }
- (void)activateIgnoringOtherApps:(BOOL)value { activations++; }
@end
static AppProbe *testApp;
#undef NSApp
#define NSApp testApp
@interface DicomStudy : NSObject
@property NSArray *imageSeries;
@end
@implementation DicomStudy
@end
@interface ViewerController : NSObject
+ (void)closeAllWindows;
@end
@implementation ViewerController
+ (void)closeAllWindows { check(NSThread.isMainThread); closes++; }
@end
@interface Database : NSObject
@property NSDictionary *objects;
@property NSArray *lastIDs;
- (NSArray *)objectsWithIDs:(NSArray *)ids;
@end
@implementation Database
- (NSArray *)objectsWithIDs:(NSArray *)ids {
    check(NSThread.isMainThread); resolutions++; self.lastIDs = ids;
    NSMutableArray *result = [NSMutableArray array];
    for (id key in ids) if (self.objects[key]) [result addObject:self.objects[key]];
    return result;
}
@end
@interface BrowserController : NSObject
@property NSString *lastStudyNotOpenedReason;
@property id lastObject;
+ (instancetype)currentBrowser;
- (BOOL)displayStudy:(DicomStudy *)study object:(id)object command:(NSString *)command;
@end
@implementation BrowserController
+ (instancetype)currentBrowser { static id browser; if (!browser) browser = [self new]; return browser; }
- (BOOL)displayStudy:(DicomStudy *)study object:(id)object command:(NSString *)command {
    check(NSThread.isMainThread && [command isEqual:@"Open"]); opens++; self.lastObject = object; return YES;
}
@end
@interface Interface : NSObject
@property Database *database;
- (DicomStudy *)studyForObject:(id)object;
- (void)reportStudyNotOpened:(DicomStudy *)study;
- (void)_onMainThreadOpenObjectsWithIDs:(NSArray *)ids;
@end
@implementation Interface
- (DicomStudy *)studyForObject:(id)object { return [object isKindOfClass:DicomStudy.class] ? object : nil; }
- (void)reportStudyNotOpened:(DicomStudy *)study { refusals++; }
METHOD
@end

static void runMode(NSString *mode, double seconds) {
    NSTimer *keepAlive = [NSTimer timerWithTimeInterval:0.01 repeats:YES block:^(NSTimer *t) {}];
    [NSRunLoop.currentRunLoop addTimer:keepAlive forMode:mode];
    NSDate *until = [NSDate dateWithTimeIntervalSinceNow:seconds];
    while (until.timeIntervalSinceNow > 0) [NSRunLoop.currentRunLoop runMode:mode beforeDate:until];
    [keepAlive invalidate];
}
int main(void) { @autoreleasepool {
    [NSUserDefaults.standardUserDefaults setVolatileDomain:@{
        @"CloseAllWindowsBeforeXMLRPCOpen": @YES,
        @"bringOsiriXToFrontAfterReceivingMessage": @YES
    } forName:NSArgumentDomain];
    CFRunLoopAddCommonMode(CFRunLoopGetMain(), (__bridge CFStringRef)NSModalPanelRunLoopMode);
    testApp = [AppProbe new];
    DicomStudy *first = [DicomStudy new], *second = [DicomStudy new];
    first.imageSeries = @[@1]; second.imageSeries = @[@2];
    Interface *rpc = [Interface new]; rpc.database = [Database new];
    rpc.database.objects = @{@1:first, @2:second};

    [rpc _onMainThreadOpenObjectsWithIDs:@[@1]];
    check(closes == 1 && opens == 1 && activations == 1 && resolutions == 1 && refusals == 0);
    check(BrowserController.currentBrowser.lastObject == first);

    testApp.activeModal = [NSObject new];
    @autoreleasepool { [rpc _onMainThreadOpenObjectsWithIDs:[NSArray arrayWithObject:@2]]; }
    check(closes == 1 && opens == 1 && activations == 1 && resolutions == 1 && refusals == 0);
    int beforeModalLoop = modalReads;
    runMode(NSModalPanelRunLoopMode, 0.25);
    check(modalReads == beforeModalLoop); // no timer work in the modal/common mode
    check(opens == 1 && closes == 1);

    // A nested default loop must recheck instead of assuming the modal ended.
    runMode(NSDefaultRunLoopMode, 0.25);
    check(modalReads > beforeModalLoop && opens == 1 && closes == 1 && activations == 1);
    testApp.activeModal = nil;
    runMode(NSDefaultRunLoopMode, 0.3);
    check(closes == 2 && opens == 2 && activations == 2 && resolutions == 2 && refusals == 0);
    check([rpc.database.lastIDs isEqual:@[@2]] && BrowserController.currentBrowser.lastObject == second);
    runMode(NSDefaultRunLoopMode, 0.2);
    check(opens == 2 && closes == 2); // delivered exactly once

    [rpc _onMainThreadOpenObjectsWithIDs:@[@99]];
    check(opens == 2 && refusals == 1); // existing missing-study reporting survives
    puts("PASS: modal/default loops, no hidden UI side effects, retained IDs, one delivery after dismissal and missing-study reporting");
}}
'''.replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-xmlrpc-modal-') as folder:
    folder = Path(folder)
    (folder/'test.m').write_text(driver)
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-framework', 'AppKit',
                    str(folder/'test.m'), '-o', str(folder/'test')], check=True)
    subprocess.run([str(folder/'test')], check=True)
