#!/usr/bin/env python3
"""Exercise actual codec launcher methods with controlled process outcomes."""
from pathlib import Path
import subprocess, sys, tempfile
root = Path(__file__).resolve().parents[1]
source = (subprocess.check_output(['git', 'show', sys.argv[1]+':Horos/Sources/DicomDatabase+DCMTK.mm']) if len(sys.argv)>1 else (root/'Horos/Sources/DicomDatabase+DCMTK.mm').read_bytes()).decode('latin1')
methods=[]
for name,arg in [('compress','paths'),('decompress','files')]:
    start=source.index(f'+(BOOL){name}DicomFilesAtPaths:(NSArray*){arg} intoDirAtPath:')
    end=source.index('    //',source.index('[thread exitOperation];',start))
    methods.append(source[start:end]+'}\n')
program=r'''
#import <Foundation/Foundation.h>
static int scenario, launches, waits;
@interface NSThread (Test)
@property double progress;
- (void)enterOperation;
- (void)exitOperation;
@end
@implementation NSThread (Test)
- (double)progress{return 0;}
- (void)setProgress:(double)value{}
- (void)enterOperation{}
- (void)exitOperation{}
@end
@interface TestTask : NSObject
- (void)setLaunchPath:(id)p;
- (void)setArguments:(id)a;
- (void)launch;
- (BOOL)isRunning;
- (void)terminate;
- (void)waitUntilExit;
- (int)terminationStatus;
- (NSTaskTerminationReason)terminationReason;
@end
@implementation TestTask
- (void)setLaunchPath:(id)p{}
- (void)setArguments:(id)a{}
- (void)launch{launches++;if(scenario==2)[NSException raise:@"launch" format:@"missing executable"];}
- (BOOL)isRunning{return scenario==3;}
- (void)terminate{}
- (void)waitUntilExit{waits++;}
- (int)terminationStatus{return scenario==1 || scenario==4 || (scenario==5 && launches==1)?7:0;}
- (NSTaskTerminationReason)terminationReason{return scenario==4?NSTaskTerminationReasonUncaughtSignal:NSTaskTerminationReasonExit;}
@end
@interface TestDate:NSObject
+ (NSTimeInterval)timeIntervalSinceReferenceDate;
@end
@implementation TestDate
+ (NSTimeInterval)timeIntervalSinceReferenceDate{static double now=0;now+=1000;return now;}
@end
#define NSTask TestTask
#define NSDate TestDate
#define CHUNK_SUBPROCESS 1
#define TIMEOUT 1
#define N2LogStackTrace(...) do {} while(0)
#define N2LogExceptionWithStackTrace(...) do {} while(0)
@interface DicomDatabase:NSObject
+ (id)defaultDatabase;
- (NSString*)errorsDirPath;
@end
@implementation DicomDatabase
+ (id)defaultDatabase{return nil;}
- (NSString*)errorsDirPath{return nil;}
METHODS
@end
int main(){@autoreleasepool{
 [[NSUserDefaults standardUserDefaults] setBool:NO forKey:@"DELETEFILELISTENER"];
 for(int mode=0;mode<2;mode++)for(scenario=0;scenario<6;scenario++){
  launches=waits=0;
  BOOL ok=mode?[DicomDatabase decompressDicomFilesAtPaths:@[@"a",@"b"] intoDirAtPath:nil]:[DicomDatabase compressDicomFilesAtPaths:@[@"a",@"b"] intoDirAtPath:nil];
  if(ok!=(scenario==0) || launches!=2){
   fprintf(stderr,"FAIL mode=%d scenario=%d result=%d launches=%d waits=%d\n",mode,scenario,ok,launches,waits);return 1;
  }
 }
 puts("PASS: both codec launchers report exit errors, launch exceptions, timeouts, signals and earlier chunk failure");
}}
'''.replace('METHODS','\n'.join(methods))
with tempfile.TemporaryDirectory(prefix='horos-codec-result-') as folder:
    p=Path(folder);(p/'test.m').write_text(program)
    subprocess.run(['xcrun','clang','-Wno-incompatible-pointer-types','-fsanitize=address',str(p/'test.m'),'-framework','Foundation','-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
