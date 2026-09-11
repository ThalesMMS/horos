#!/usr/bin/env python3
"""Exercise actual completion count/gate against a temporary filesystem."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1];s=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
a=s.index('        for (NSString *exportedPath in exportedPaths)');b=s.index('\n\n',a);count=s[a:b]
a=s.index('        if (!exportAborted && ![NSThread currentThread].isCancelled');b=s.index('\n    }',a);gate=s[a:b]
program=r'''
#import <Foundation/Foundation.h>
static BOOL cancelled;
@interface TestThread:NSObject
+ (TestThread*)currentThread;
- (BOOL)isCancelled;
@end
@implementation TestThread
+ (TestThread*)currentThread{static TestThread *t=nil;if(!t)t=[TestThread new];return t;}
- (BOOL)isCancelled{return cancelled;}
@end
#define NSThread TestThread
@interface Probe:NSObject
- (BOOL)run:(NSString*)location scenario:(int)scenario;
@end
@implementation Probe
- (void)showDICOMExportCompletion:(NSDictionary*)result{[result writeToFile:[result[@"location"] stringByAppendingPathComponent:@"result.plist"] atomically:YES];}
- (BOOL)run:(NSString*)location scenario:(int)scenario{
 BOOL exportAborted=scenario==1;cancelled=scenario==2;
 NSDictionary *parameters=@{@"showCompletion":@(scenario!=3)};
 NSString *existing=[location stringByAppendingPathComponent:@"image.dcm"],*missing=[location stringByAppendingPathComponent:@"removed.dcm"];
 NSMutableSet *exportedPaths=[NSMutableSet setWithObject:missing];
 if(scenario!=4){[@"bytes" writeToFile:existing atomically:YES encoding:NSUTF8StringEncoding error:NULL];[exportedPaths addObject:existing];[exportedPaths addObject:existing];}
 NSUInteger exportedCount=0;
 COUNT
 GATE
 NSDictionary *result=[NSDictionary dictionaryWithContentsOfFile:[location stringByAppendingPathComponent:@"result.plist"]];
 return scenario==0 ? [result[@"count"] unsignedIntegerValue]==1 && [result[@"location"] isEqual:location] : result==nil;
}
@end
int main(int argc,char **argv){@autoreleasepool{Probe *probe=[Probe new];
 for(int i=0;i<5;i++){NSString *p=[[NSString stringWithUTF8String:argv[1]] stringByAppendingPathComponent:[NSString stringWithFormat:@"%d",i]];[[NSFileManager defaultManager] createDirectoryAtPath:p withIntermediateDirectories:YES attributes:nil error:NULL];if(![probe run:p scenario:i])return 1;}
 [probe release];puts("PASS: surviving files counted once; abort, cancel, internal caller and empty result suppress completion");
}}
'''.replace('COUNT',count).replace('GATE',gate)
with tempfile.TemporaryDirectory(prefix='horos-completion-') as folder:
 p=Path(folder);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'files')],check=True)
