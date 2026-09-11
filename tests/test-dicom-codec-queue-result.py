#!/usr/bin/env python3
"""Exercise the actual conversion queue with real NSInvocationOperations."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
a=s.index('-(NSNumber*)_processFilesAtPaths_processChunk:')
b=s.index('-(void)threadBridgeForProcessFilesAtPaths:',a)
browser=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
c=browser.index('            if (compressionMatrixSelectedTag == 1 || compressionMatrixSelectedTag == 2)',browser.index('        if( [files2Compress count] > 0 && exportAborted == NO)'))
caller=browser[c:browser.index('#endif',c)]
program=r'''
#import <Foundation/Foundation.h>
#define Compress 0
#define Decompress 1
#define N2LocalizedSingularPluralCount(...) @"files"
#define N2LogExceptionWithStackTrace(...) do {} while(0)
@interface NSThread (Test)
@property double progress;
@property(copy) NSString *status;
@end
@implementation NSThread (Test)
- (double)progress{return 0;}
- (void)setProgress:(double)x{}
- (NSString*)status{return nil;}
- (void)setStatus:(NSString*)x{}
@end
@interface NSArray (Test)
- (NSArray*)splitArrayIntoArraysOfMinSize:(NSUInteger)n maxArrays:(NSUInteger)m;
@end
@implementation NSArray (Test)
- (NSArray*)splitArrayIntoArraysOfMinSize:(NSUInteger)n maxArrays:(NSUInteger)m{
 NSMutableArray *a=[NSMutableArray array];for(id x in self)[a addObject:@[x]];return a;
}
@end
@interface ThreadsManager:NSObject
+ (id)defaultManager;
- (void)addThreadAndStart:(id)t;
@end
@implementation ThreadsManager
+ (id)defaultManager{return nil;}
- (void)addThreadAndStart:(id)t{}
@end
@interface DicomDatabase:NSObject {NSLock *_processFilesLock;}
- (BOOL)processFilesAtPaths:(NSArray*)p intoDirAtPath:(NSString*)d mode:(int)m error:(NSError**)e;
@end
@implementation DicomDatabase
- (id)init{self=[super init];if(self)_processFilesLock=[NSLock new];return self;}
- (void)dealloc{[_processFilesLock release];[super dealloc];}
+ (BOOL)compressDicomFilesAtPaths:(NSArray*)p intoDirAtPath:(NSString*)d{
 if([p containsObject:@"exception"])[NSException raise:@"codec" format:@"failure"];
 return ![p containsObject:@"failure"];
}
+ (BOOL)decompressDicomFilesAtPaths:(NSArray*)p intoDirAtPath:(NSString*)d{return [self compressDicomFilesAtPaths:p intoDirAtPath:d];}
METHODS
@end
@interface ExportProbe:NSObject {int alerts;}
- (BOOL)run:(DicomDatabase*)idatabase files:(NSArray*)files2Compress tag:(NSInteger)compressionMatrixSelectedTag;
@end
@implementation ExportProbe
- (void)showDICOMExportError:(NSError*)error{if(error.localizedDescription.length)alerts++;}
- (BOOL)run:(DicomDatabase*)idatabase files:(NSArray*)files2Compress tag:(NSInteger)compressionMatrixSelectedTag{
 alerts=0;BOOL exportAborted=NO;
 CALLER
 if(alerts!=(exportAborted?1:0))[NSException raise:@"alert" format:@"missing error"];
 return exportAborted;
}
@end
int main(){@autoreleasepool{
 DicomDatabase *db=[DicomDatabase new];
 NSArray *cases=@[@[],@[@"ok"],@[@"ok",@"failure",@"ok"],@[@"ok",@"exception",@"ok"]];
 for(int mode=0;mode<2;mode++)for(int i=0;i<4;i++){
  NSError *error=nil;BOOL ok=[db processFilesAtPaths:cases[i] intoDirAtPath:nil mode:mode error:&error];
  if(ok!=(i<2) || (i>=2 && !error.localizedFailureReason.length))return 1;
  if(![db processFilesAtPaths:@[@"ok"] intoDirAtPath:@"destination" mode:mode error:NULL])return 2;
 }
 ExportProbe *probe=[ExportProbe new];
 for(int tag=0;tag<3;tag++){
  if([probe run:db files:@[@"failure"] tag:tag]!=(tag!=0))return 3;
  if([probe run:db files:@[@"ok"] tag:tag])return 4;
 }
 [probe release];
 [db release];puts("PASS: both real operation queues propagate failures/exceptions and unlock for subsequent work");
}}
'''.replace('METHODS',s[a:b]).replace('CALLER',caller)
with tempfile.TemporaryDirectory(prefix='horos-codec-queue-') as folder:
 p=Path(folder);(p/'test.mm').write_text(program)
 subprocess.run(['xcrun','clang++','-fsanitize=address',str(p/'test.mm'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
