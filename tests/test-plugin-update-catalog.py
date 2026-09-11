#!/usr/bin/env python3
"""Run the production plugin update scans with controlled catalog transport."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
source=(root/'Horos/Sources/PluginManager.m').read_bytes().decode('latin1')
methods=[]
for marker in ['- (NSArray*)checkForHorosPluginsUpdates:', '- (NSArray*) checkForOsiriXPluginsUpdates:']:
 start=source.index(marker);end=source.index('\n}',start)+2
 methods.append(source[start:end].replace('HorosLoadPluginCatalog(', 'FixtureLoad('))
program=r'''
#import <Foundation/Foundation.h>
#import "HorosPluginCatalog.h"
#define HOROS_PLUGIN_LIST_URL @"http://127.0.0.1/catalog"
#define HOROS_PLUGIN_LIST_ALT_URL HOROS_PLUGIN_LIST_URL
#define OSIRIX_PLUGIN_LIST_URL HOROS_PLUGIN_LIST_URL
#define OSIRIX_PLUGIN_LIST_ALT_URL HOROS_PLUGIN_LIST_URL
static int calls,mode;
static NSArray *input;
static dispatch_semaphore_t done;
static NSArray *FixtureLoad(NSURL *url,NSTimeInterval timeout,NSError **error) {
 NSCAssert(!NSThread.isMainThread,@"Update scans must load on worker");NSCAssert(timeout==10,@"Bounded timeout required");calls++;
 if(mode==0) { if(error)*error=[NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorTimedOut userInfo:nil];return nil; }
 return input;
}
@interface PluginManager:NSObject
+ (NSArray*)pluginsList;
+ (NSComparisonResult)compareVersion:(NSString*)a withVersion:(NSString*)b;
- (NSArray*)checkForHorosPluginsUpdates:(id)sender;
- (NSArray*)checkForOsiriXPluginsUpdates:(id)sender;
- (void)run;
@end
@implementation PluginManager
+ (NSArray*)pluginsList { return @[@{@"name":@"Synthetic",@"version":@"1.0"}]; }
+ (NSComparisonResult)compareVersion:(NSString*)a withVersion:(NSString*)b { return HorosComparePluginVersions(a,b); }
METHODS
- (void)run { @autoreleasepool {
 for(mode=0;mode<4;mode++) {
  input=mode==1?@[]:@[@{@"name":@"Synthetic",@"version":mode==3?@"1.0":@"2.0",@"download_url":@"https://example.invalid/Synthetic.horosplugin.zip"}];
  calls=0;
  NSArray *horos=[self checkForHorosPluginsUpdates:nil];NSArray *osirix=[self checkForOsiriXPluginsUpdates:nil];
  NSCAssert(calls==2,@"Duplicate fallback URLs should not be retried");
  NSCAssert(horos.count==(mode==2?1:0) && osirix.count==(mode==2?1:0),@"Incorrect update result");
  NSCAssert(input.count==(mode==1?0:1),@"Update matching mutated the shared catalog");
 }
 puts("PASS: failed/empty/current/newer catalogs, deduplicated endpoints, timeout and immutable input; scans only propose updates");
 dispatch_semaphore_signal(done);
} }
@end
int main(){@autoreleasepool{done=dispatch_semaphore_create(0);[NSThread detachNewThreadSelector:@selector(run) toTarget:[PluginManager new] withObject:nil];dispatch_semaphore_wait(done,DISPATCH_TIME_FOREVER);}return 0;}
'''.replace('METHODS','\n'.join(methods))
with tempfile.TemporaryDirectory(prefix='horos-update-catalog-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fblocks','-framework','Foundation','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,timeout=10)
