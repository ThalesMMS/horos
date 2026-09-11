#!/usr/bin/env python3
"""Run production catalog getters to ensure failed preloads are not retried by UI callbacks."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
source=(root/'Horos/Sources/PluginManagerController.m').read_bytes().decode('latin1')
methods=[]
for kind in ['OsiriX','Horos']:
 start=source.index(f'- (NSArray*) available{kind}Plugins;')
 end=source.index('\n}',start)+2
 methods.append(source[start:end].replace('HorosLoadPluginCatalog(', 'FixtureLoad('))
program=r'''
#import <Foundation/Foundation.h>
#import "HorosPluginCatalog.h"
static NSArray *CachedOsiriXPluginsList, *CachedHorosPluginsList;
static NSDate *CachedOsiriXPluginsListDate, *CachedHorosPluginsListDate;
static int calls;
static BOOL empty;
static dispatch_semaphore_t finished;
NSInteger sortPluginArrayByName(id a,id b,void *c) { return [[a objectForKey:@"name"] compare:[b objectForKey:@"name"]]; }
@interface FixtureTransport:NSObject
+ (NSArray*)arrayWithContentsOfURL:(NSURL*)url;
@end
@implementation FixtureTransport
+ (NSArray*)arrayWithContentsOfURL:(NSURL*)url { calls++; return empty ? @[] : nil; }
@end
static NSArray *FixtureLoad(NSURL *url, NSTimeInterval timeout, NSError **error) { return [FixtureTransport arrayWithContentsOfURL:url]; }
@interface Controller:NSObject { NSArray *osirixPluginListURLs,*horosPluginListURLs; NSError *osirixCatalogError,*horosCatalogError; }
- (NSArray*)availableOsiriXPlugins;
- (NSArray*)availableHorosPlugins;
- (void)preload;
@end
@implementation Controller
- (id)init { self=[super init]; osirixPluginListURLs=[@[@"http://127.0.0.1/first",@"http://127.0.0.1/second"] retain];horosPluginListURLs=[osirixPluginListURLs retain];return self; }
- (void)preload { @autoreleasepool { NSCAssert(!NSThread.isMainThread,@"Expected worker");[self availableOsiriXPlugins];[self availableHorosPlugins];dispatch_semaphore_signal(finished); } }
METHODS
@end
int main() { @autoreleasepool {
 NSCAssert(NSThread.isMainThread,@"Expected main thread"); Controller *controller=[Controller new];
 finished=dispatch_semaphore_create(0);
 [NSThread detachNewThreadSelector:@selector(preload) toTarget:controller withObject:nil];
 dispatch_semaphore_wait(finished,DISPATCH_TIME_FOREVER);
 NSCAssert(calls==4,@"Worker tries two fallback endpoints per catalog");
 for(int i=0;i<4;i++) { NSCAssert([controller availableOsiriXPlugins]==nil,@"Failure remains nil");NSCAssert([controller availableHorosPlugins]==nil,@"Failure remains nil"); }
 NSCAssert(calls==4,@"UI retried failed network requests");
 empty=YES;
 [NSThread detachNewThreadSelector:@selector(preload) toTarget:controller withObject:nil];
 dispatch_semaphore_wait(finished,DISPATCH_TIME_FOREVER);
 NSCAssert(calls==6,@"Worker loads one valid empty catalog per type");
 NSCAssert([controller availableOsiriXPlugins]!=nil && [controller availableHorosPlugins]!=nil,@"Valid empty cache is distinct from failure");
 NSCAssert(calls==6,@"UI must use cache");
 puts("PASS: failed worker preload is never retried on main; valid empty cache remains available without network calls");
} }
'''.replace('METHODS','\n'.join(methods))
with tempfile.TemporaryDirectory(prefix='horos-catalog-thread-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fblocks','-framework','Foundation','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,timeout=10)
