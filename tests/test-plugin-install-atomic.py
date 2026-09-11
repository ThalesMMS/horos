#!/usr/bin/env python3
"""Exercise staged plugin publication, including interruption on both sides of the swap."""
from pathlib import Path
import subprocess
import tempfile
import shutil
root=Path(__file__).resolve().parent.parent
program=r'''
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <errno.h>
#include <unistd.h>
static BOOL failPublish, interruptPublish, interruptAfterPublish, corruptStaging;
@interface QAFileManager:NSFileManager
@end
@implementation QAFileManager
+ (id)defaultManager { static id instance; if(!instance) instance=[self new]; return instance; }
- (BOOL)copyItemAtPath:(NSString*)source toPath:(NSString*)destination error:(NSError**)error {
 BOOL result=[super copyItemAtPath:source toPath:destination error:error];
 if(result && corruptStaging)
  [@"Corrupted staged resource" writeToFile:[destination stringByAppendingPathComponent:@"Contents/Resources/seal.txt"] atomically:YES encoding:NSUTF8StringEncoding error:NULL];
 return result;
}
@end
static int publish(const char *source, const char *destination, unsigned int flags) {
 if(interruptPublish) _exit(77);
 if(failPublish) { errno=EIO; return -1; }
 int result=renamex_np(source,destination,flags);
 if(result==0 && interruptAfterPublish) _exit(78);
 return result;
}
#define NSFileManager QAFileManager
#define renamex_np publish
#import "HorosPluginInstall.h"
#undef renamex_np
#undef NSFileManager
int main(int argc,char **argv) { @autoreleasepool {
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 NSString *source=[root stringByAppendingPathComponent:@"new/QAUniversal.horosplugin"];
 NSString *destination=[root stringByAppendingPathComponent:@"installed/QAUniversal.horosplugin"];
 NSString *payload=@"Contents/Resources/seal.txt";
 NSData *old=[NSData dataWithContentsOfFile:[destination stringByAppendingPathComponent:payload]];
 NSData *updated=[NSData dataWithContentsOfFile:[source stringByAppendingPathComponent:payload]];
 NSCAssert(old && updated && ![old isEqual:updated],@"Fixture versions must differ");
 NSError *error=nil;
 if(argc>2) {
  interruptPublish=strcmp(argv[2],"interrupt")==0;
  interruptAfterPublish=!interruptPublish;
  HorosInstallPlugin(source,destination,&error); return 1;
 }
 NSCAssert(!HorosInstallPlugin([root stringByAppendingPathComponent:@"missing"],destination,&error),@"Missing source must fail");
 NSCAssert([[NSData dataWithContentsOfFile:[destination stringByAppendingPathComponent:payload]] isEqual:old],@"Copy failure must preserve old version");
 corruptStaging=YES; error=nil;
 NSCAssert(!HorosInstallPlugin(source,destination,&error),@"Corrupted staged signature must be rejected");
 NSCAssert([[NSData dataWithContentsOfFile:[destination stringByAppendingPathComponent:payload]] isEqual:old],@"Staged corruption must preserve old version");
 NSCAssert([[NSData dataWithContentsOfFile:[source stringByAppendingPathComponent:payload]] isEqual:updated],@"Staging corruption must not modify source");
 corruptStaging=NO;
 failPublish=YES; error=nil;
 NSCAssert(!HorosInstallPlugin(source,destination,&error) && error.code==EIO,@"Publication failure must be reported");
 NSCAssert([[NSData dataWithContentsOfFile:[destination stringByAppendingPathComponent:payload]] isEqual:old],@"Failed swap must preserve old version");
 failPublish=NO;
 NSCAssert(HorosInstallPlugin(source,destination,&error),@"Valid swap should succeed: %@",error);
 NSCAssert([[NSData dataWithContentsOfFile:[destination stringByAppendingPathComponent:payload]] isEqual:updated],@"Published version must be complete");
 NSCAssert([[NSData dataWithContentsOfFile:[source stringByAppendingPathComponent:payload]] isEqual:updated],@"Installation must retain source");
 NSCAssert([[NSData dataWithContentsOfFile:[HorosPluginPreviousPath(destination) stringByAppendingPathComponent:payload]] isEqual:old],@"Successful update must keep the previous working plugin");
 NSString *fresh=[root stringByAppendingPathComponent:@"fresh/QAUniversal.horosplugin"];
 NSCAssert(HorosInstallPlugin(source,fresh,&error),@"Fresh installation must succeed");
 for(NSString *entry in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:destination.stringByDeletingLastPathComponent error:NULL])
  NSCAssert(![entry hasPrefix:@".horos-plugin-update-"],@"Normal completion must clean staging");
 NSCAssert(NSClassFromString(@"QAUniversal")==Nil,@"Validation must not execute plugin code");
 puts("PASS: copy failure, staged corruption, swap failure, replacement, fresh install, source preservation and staging cleanup");
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-plugin-atomic-') as directory:
 p=Path(directory)
 subprocess.run(['python3',str(root/'tools/generate-plugin-load-fixtures.py'),str(p/'fixtures')],check=True)
 (p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-framework','Foundation','-framework','Security','-fsanitize=address','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
 for mode in ('normal','interrupt','interrupt-after'):
  data=p/mode
  for parent in ('new','installed'):
   shutil.copytree(p/'fixtures/QAUniversal.horosplugin',data/parent/'QAUniversal.horosplugin')
  (data/'new/QAUniversal.horosplugin/Contents/Resources/seal.txt').write_text('Updated synthetic resource')
  subprocess.run(['codesign','--force','--sign','-',str(data/'new/QAUniversal.horosplugin')],check=True,capture_output=True)
  result=subprocess.run([str(p/'test'),str(data)]+([mode] if mode!='normal' else []),timeout=30)
  assert result.returncode==({'normal':0,'interrupt':77,'interrupt-after':78}[mode]), result.returncode
  if mode=='interrupt':
   assert (data/'installed/QAUniversal.horosplugin/Contents/Resources/seal.txt').read_text()=='Original synthetic resource'
   assert (data/'new/QAUniversal.horosplugin').exists()
   print('PASS: process exit immediately before publication leaves installed version intact')

  if mode=='interrupt-after':
   assert (data/'installed/QAUniversal.horosplugin/Contents/Resources/seal.txt').read_text()=='Updated synthetic resource'
   subprocess.run(['codesign','--verify','--deep',str(data/'installed/QAUniversal.horosplugin')],check=True,capture_output=True)
   backups=list((data/'installed').glob('.horos-plugin-update-*/QAUniversal.horosplugin/Contents/Resources/seal.txt'))
   assert len(backups)==1 and backups[0].read_text()=='Original synthetic resource'
   assert (data/'new/QAUniversal.horosplugin').exists()
   print('PASS: process exit after publication leaves complete signed update and recoverable old staging copy')
