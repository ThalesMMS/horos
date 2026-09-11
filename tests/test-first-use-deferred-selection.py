#!/usr/bin/env python3
"""A source selection queued before setup must not clear the chosen database."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
a=s.index('- (void)completeFirstUseDatabaseSetup');method=s[a:s.index('- (IBAction) clickBanner:',a)]
code=r'''
#import <Cocoa/Cocoa.h>
@interface ICloudDriveDetector:NSObject
+ (void)performStartupICloudDriveTasks:(id)browser;
@end
@implementation ICloudDriveDetector
+ (void)performStartupICloudDriveTasks:(id)browser {}
@end
@interface O2HMigrationAssistant:NSObject
+ (void)performStartupO2HTasks:(id)browser;
@end
@implementation O2HMigrationAssistant
+ (void)performStartupO2HTasks:(id)browser {}
@end
@interface Browser:NSObject
@property(retain) id database;
- (void)resetToLocalDatabase;
- (void)awakeSources;
@end
@implementation Browser
@synthesize database;
- (void)awakeSources {}
- (void)resetToLocalDatabase {self.database=@"chosen database";}
METHOD
@end
int main(void) {@autoreleasepool {
 Browser *browser=[Browser new];
 [browser performSelector:@selector(setDatabase:) withObject:nil afterDelay:0.01];
 [browser completeFirstUseDatabaseSetup];
 [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
 NSCAssert([browser.database isEqual:@"chosen database"],@"Queued nil selection cleared the chosen database");
 NSLog(@"PASS: setup cancels stale queued nil source selection");
}}
'''.replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-first-use-selection-') as tmp:
 p=Path(tmp);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-framework','Cocoa',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
