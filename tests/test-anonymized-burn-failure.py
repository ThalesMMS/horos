#!/usr/bin/env python3
"""Execute production media preparation with a failed anonymization result.
No media writer runs: the test verifies the boundary before content preparation.
"""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/BurnerWindowController.m').read_bytes().decode('latin1')
method=s[s.index('- (void)performBurn:'):s.index('- (IBAction) setAnonymizedCheck:')]
harness=r'''
#import <Cocoa/Cocoa.h>
static NSInteger prepared,alerts;
static NSString *mode;
static void check(BOOL ok) { if(!ok) abort(); }
static NSInteger fixtureAlert(NSString *a,NSString *b,NSString *c,id d,id e,...) { alerts++;return 0; }
#define NSRunCriticalAlertPanel fixtureAlert
#define DMGFile 0
#define CDDVD 1
#define USBKey 2
@interface HorosAnonymizationErrorPresenter : NSObject
+ (void)presentError:(NSError *)error;
@end
@implementation HorosAnonymizationErrorPresenter
+ (void)presentError:(NSError *)error { alerts++; }
@end
@interface DicomDatabase : NSObject
- (id)independentDatabase; - (NSArray *)objectsWithIDs:(NSArray *)ids;
@end
@implementation DicomDatabase
- (id)independentDatabase { return self; } - (NSArray *)objectsWithIDs:(NSArray *)ids { return ids; }
@end
@interface BrowserController : NSObject
+ (id)currentBrowser; - (DicomDatabase *)database;
@end
@implementation BrowserController
+ (id)currentBrowser { static id b; if(!b)b=[self new];return b; }
- (DicomDatabase *)database { static id d;if(!d)d=[DicomDatabase new];return d; }
@end
@interface Anonymization : NSObject
+ (NSDictionary *)anonymizeFiles:(NSArray *)files dicomImages:(NSArray *)images toPath:(NSString *)path withTags:(NSArray *)tags error:(NSError **)error;
@end
@implementation Anonymization
+ (NSDictionary *)anonymizeFiles:(NSArray *)files dicomImages:(NSArray *)images toPath:(NSString *)path withTags:(NSArray *)tags error:(NSError **)error {
 if([mode isEqual:@"success"])return @{@"source":@"anonymous"};
 if(![mode isEqual:@"nil-error"]) *error=[NSError errorWithDomain:NSCocoaErrorDomain code:[mode isEqual:@"cancel"]?NSUserCancelledError:NSFileWriteNoPermissionError userInfo:nil];
 return nil;
}
@end
@interface BurnerWindowController : NSObject {
 NSArray *files,*dbObjectsID,*originalDbObjectsID,*anonymizationTags;
 NSMutableArray *anonymizedFiles;
 BOOL isSettingUpBurn,runBurnAnimation,burning,cancelled,failed;
 NSString *writeDMGPath,*burnFailure,*writeVolumePath;
}
@property BOOL buttonsDisabled;
- (void)prepareCDContent:(id)a :(id)b;
- (NSString *)folderToBurn;
- (NSWindow *)window;
- (void)run;
@end
@implementation BurnerWindowController
- (void)prepareCDContent:(id)a :(id)b { prepared++; }
- (BOOL)createDMG:(NSString *)image withSource:(NSString *)folder { return YES; }
- (BOOL)saveOnVolume { return YES; }
- (NSString *)folderToBurn { return @"/nonexistent-horos-test-media-folder"; }
- (NSWindow *)window { return nil; }
METHOD
- (void)run {
 files=@[@"source"];dbObjectsID=originalDbObjectsID=@[@1];anonymizationTags=@[@1];
 self.buttonsDisabled=YES;runBurnAnimation=burning=YES;cancelled=YES;
 [self performBurn:nil];
 for(int i=0;i<10;i++) [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
 check(prepared==([mode isEqual:@"success"]?1:0));
 check(alerts==([mode isEqual:@"success"]||[mode isEqual:@"cancel"]?0:1));
 check(!self.buttonsDisabled&&!isSettingUpBurn&&!runBurnAnimation&&!burning);
}
@end
int main(int argc,char **argv){@autoreleasepool{mode=[NSString stringWithUTF8String:argv[1]];[[BurnerWindowController new] run];NSLog(@"PASS %@: preparation gate and UI reset",mode);}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-burn-anonymization-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(harness)
 subprocess.run(['xcrun','clang','-fblocks','-Wno-objc-method-access','-Wno-deprecated-declarations','-framework','Cocoa',str(p/'test.m'),'-o',str(p/'test')],check=True)
 for mode in ['failure','nil-error','cancel','success']:
  subprocess.run([str(p/'test'),mode],check=True)
