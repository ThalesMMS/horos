#!/usr/bin/env python3
"""Execute the database plugin dispatch method with controlled plugin failures."""
import argparse
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path)
parser.add_argument('--viewer',action='store_true')
args=parser.parse_args()
source=args.source or root/('Horos/Sources/ViewerController.m' if args.viewer else 'Horos/Sources/BrowserController.m')
s=source.read_bytes().decode('latin1')
a=s.index('- (void)executeFilterFromBundle:' if args.viewer else '- (void)executeFilterFromString: (NSString*)name')
method=s[a:s.index('\n- (void)executeFilter:(id)sender' if args.viewer else '\n- (void)executeFilterDB:',a)]
program=r'''
#import <Foundation/Foundation.h>
#include <stdarg.h>
static int depth, processed, prepared;
static long prepareCode, processCode;
static BOOL throwPrepare, throwProcess;
static NSString *lastAlert;
static NSMutableDictionary *registry;
#define N2LogExceptionWithStackTrace(e) ((void)0)
static NSInteger NSRunAlertPanel(NSString *title,NSString *format,id a,id b,id c,...) {
 va_list args;va_start(args,c);lastAlert=[[[NSString alloc] initWithFormat:format arguments:args] autorelease];va_end(args);return 1;
}
@interface PluginManager:NSObject
+ (id)plugins;
+ (void)startProtectForCrashWithFilter:(id)filter;
+ (void)endProtectForCrash;
@end
@implementation PluginManager
+ (id)plugins { return registry; }
+ (void)startProtectForCrashWithFilter:(id)filter {depth++;}
+ (void)endProtectForCrash {depth--;}
@end
@interface Filter:NSObject
- (long)prepareFilter:(id)viewer;
- (long)filterImage:(NSString*)name;
@end
@implementation Filter
- (long)prepareFilter:(id)viewer {prepared++;if(throwPrepare) [NSException raise:@"SyntheticPreparation" format:@"Missing synthetic dependency"];return prepareCode;}
- (long)filterImage:(NSString*)name {processed++;if(throwProcess) [NSException raise:@"SyntheticProcessing" format:@"Synthetic processing failure"];return processCode;}
@end
@interface BrowserController:NSObject
- (void)executeFilterFromString:(NSString*)name;
@end
@implementation BrowserController
METHOD
@end
int main() { @autoreleasepool {
 registry=[NSMutableDictionary new];BrowserController *browser=[BrowserController new];
 [browser executeFilterFromString:@"Absent"];
 NSCAssert(depth==0 && processed==0 && lastAlert!=nil,@"Missing plugin must be explained");
 registry[@"QA"]=[Filter new];
 prepareCode=42;lastAlert=nil;
 [browser executeFilterFromString:@"QA"];
 NSCAssert(processed==0 && depth==0,@"Preparation failure must prevent processing and clear marker");
 NSCAssert([lastAlert containsString:@"preparation"] && [lastAlert containsString:@"42"],@"Preparation error needs phase and code");
 prepareCode=0;throwPrepare=YES;lastAlert=nil;
 [browser executeFilterFromString:@"QA"];
 NSCAssert(processed==0 && depth==0 && [lastAlert containsString:@"SyntheticPreparation"],@"Preparation exception must be caught and marker cleared");
 throwPrepare=NO;processCode=7;lastAlert=nil;
 [browser executeFilterFromString:@"QA"];
 NSCAssert(processed==1 && depth==0 && [lastAlert containsString:@"processing"] && [lastAlert containsString:@"7"],@"Processing status must not be ignored");
 processCode=0;throwProcess=YES;lastAlert=nil;
 [browser executeFilterFromString:@"QA"];
 NSCAssert(processed==2 && depth==0 && [lastAlert containsString:@"SyntheticProcessing"],@"Processing exception must clear marker");
 throwProcess=NO;lastAlert=nil;
 [browser executeFilterFromString:@"QA"];
 NSCAssert(processed==3 && depth==0 && lastAlert==nil,@"Successful filter must execute normally");
 puts("PASS: missing filter, prepare failure/exception, processing failure/exception, success and crash-marker cleanup");
} }
'''.replace('METHOD',method)
if args.viewer:
 program=program.replace('@interface BrowserController:NSObject', '@interface BrowserController:NSObject { id imageView; }\n- (void)executeFilterFromBundle:(NSBundle*)bundle title:(NSString*)name;\n- (void)checkEverythingLoaded;\n- (void)computeInterval;')
 program=program.replace('@implementation BrowserController', '@implementation BrowserController\n- (void)executeFilterFromString:(NSString*)name { [self executeFilterFromBundle:nil title:name]; }\n- (void)checkEverythingLoaded {}\n- (void)computeInterval {}')
 program=program.replace('@interface BrowserController', '#define OsirixRecomputeROINotification @"SyntheticRecomputeROI"\n@interface AppController:NSObject\n+ (BOOL)willExecutePlugin:(id)filter;\n@end\n@implementation AppController\n+ (BOOL)willExecutePlugin:(id)filter { return YES; }\n@end\n@interface BrowserController',1)
with tempfile.TemporaryDirectory(prefix='horos-plugin-execution-') as directory:
 p=Path(directory);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-framework','Foundation','-fsanitize=address',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,timeout=30)
