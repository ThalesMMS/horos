#!/usr/bin/env python3
"""Execute the actual ZIP method against /usr/bin/zip and inspect resulting archives."""
from pathlib import Path
import subprocess,tempfile,zipfile,sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('+ (BOOL) prepareProtectedEmailAttachment:');b=s.index('\n#ifdef OSIRIX_VIEWER',a)
code=r'''
#import <Cocoa/Cocoa.h>
#define N2LogExceptionWithStackTrace(e) ((void)0)
@interface AppController:NSObject
+ (BOOL)hasMacOSXSnowLeopard;
@end
@implementation AppController
+ (BOOL)hasMacOSXSnowLeopard{return YES;}
@end
@interface NSThread(Status)
@property(copy) NSString *status;
@end
@implementation NSThread(Status)
- (void)setStatus:(NSString*)value{}
- (NSString*)status{return @"";}
@end
@interface WaitRendering:NSObject
- (id)init:(NSString*)message;
- (void)showWindow:(id)sender;
- (void)close;
@end
@implementation WaitRendering
- (id)init:(NSString*)message{return [super init];}
- (void)showWindow:(id)sender{}
- (void)close{}
@end
@interface BrowserController:NSObject
+ (BOOL)encryptFileOrFolder:(NSString*)source inZIPFile:(NSString*)destination password:(NSString*)password deleteSource:(BOOL)remove showGUI:(BOOL)gui error:(NSError**)error;
@end
@implementation BrowserController
BODY
@end
int main(int argc,char **argv){@autoreleasepool{
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 for(int scenario=0;scenario<9;scenario++) {
  NSString *folder=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"source %d",scenario]];
  [[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:NULL];
  NSString *file=[folder stringByAppendingPathComponent:@"image.txt"];
  [@"synthetic archive bytes" writeToFile:file atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  NSString *dest=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"result-%d.zip",scenario]];
  if(scenario==2)dest=[file stringByAppendingPathComponent:@"invalid.zip"];
  NSString *source=(scenario==3 || scenario==6)?[root stringByAppendingPathComponent:@"missing"]:folder;
  if(scenario==4)dest=nil;
  if(scenario==0 || scenario==6 || scenario==8)[@"old archive bytes" writeToFile:dest atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  if(scenario==7) {
   [[NSFileManager defaultManager] createDirectoryAtPath:dest withIntermediateDirectories:YES attributes:nil error:NULL];
   [@"destination folder sentinel" writeToFile:[dest stringByAppendingPathComponent:@"keep.txt"] atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  }
  if(scenario==8)[[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions:@0} ofItemAtPath:file error:NULL];
  NSError *error=nil;BOOL removeSource=scenario==1 || scenario==2 || scenario==5 || scenario==6 || scenario==7 || scenario==8;
  BOOL ok=[BrowserController encryptFileOrFolder:source inZIPFile:dest password:scenario==5?@"synthetic-password":@"" deleteSource:removeSource showGUI:NO error:&error];
  if(scenario==8)[[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions:@0644} ofItemAtPath:file error:NULL];
  BOOL expected=scenario==0 || scenario==1 || scenario==5;
  if(ok!=expected || (!!error)==expected || (!expected && !error.localizedDescription.length)) {fprintf(stderr,"FAIL scenario %d: success %d error %s\n",scenario,ok,[[error description] UTF8String]);return 1;}
  if((scenario==6 || scenario==8) && ![[NSString stringWithContentsOfFile:dest encoding:NSUTF8StringEncoding error:NULL] isEqual:@"old archive bytes"]) {fputs("FAIL previous archive lost after failed export\n",stderr);return 1;}
  if(scenario==7 && ![[NSString stringWithContentsOfFile:[dest stringByAppendingPathComponent:@"keep.txt"] encoding:NSUTF8StringEncoding error:NULL] isEqual:@"destination folder sentinel"])return 1;
  BOOL sourceRemains=[[NSFileManager defaultManager] fileExistsAtPath:file];
  if(sourceRemains!=(scenario!=1 && scenario!=5)) {fputs("FAIL source preservation\n",stderr);return 1;}
 }
 NSError *emailError=nil;
 NSString *original=[root stringByAppendingPathComponent:@"result-5.zip"];
 NSString *email=[root stringByAppendingPathComponent:@"Images.zip"];
 if(![BrowserController prepareProtectedEmailAttachment:original destination:email password:@"synthetic-password" error:&emailError])return 2;
 NSData *saved=[NSData dataWithContentsOfFile:email];
 if([BrowserController prepareProtectedEmailAttachment:original destination:email password:@"" error:&emailError] || !emailError)return 3;
 if(![saved isEqual:[NSData dataWithContentsOfFile:email]])return 4;
 if([BrowserController prepareProtectedEmailAttachment:@"/missing-source" destination:email password:@"synthetic-password" error:&emailError] || !emailError)return 5;
 if(![saved isEqual:[NSData dataWithContentsOfFile:email]])return 6;
 if(![[NSFileManager defaultManager] fileExistsAtPath:original])return 7;
 puts("PASS: ZIP result and NSError; failed sources preserved; successful deleteSource honored");
}}
'''.replace('BODY',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-zip-result-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','swiftc','-emit-library','-emit-objc-header','-emit-objc-header-path',str(p/'Archive-Swift.h'),'-module-name','Archive',str(root/'Horos/Sources/ExportArchive.swift'),'-o',str(p/'libArchive.dylib')],check=True)
 subprocess.run(['xcrun','clang','-include',str(p/'Archive-Swift.h'),'-L'+str(p),'-lArchive','-Wl,-rpath,'+str(p),'-fsanitize=address','-Wno-deprecated-declarations',str(p/'test.m'),'-framework','Cocoa','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'files')],check=True)
 for case in [0,1,5]:
  with zipfile.ZipFile(p/'files'/f'result-{case}.zip') as z:
   assert z.read(f'source {case}/image.txt',pwd=b'synthetic-password' if case==5 else None)==b'synthetic archive bytes'
   if case==5:assert z.getinfo(f'source {case}/image.txt').flag_bits & 1
 import io
 with zipfile.ZipFile(p/'files'/'Images.zip') as outer:
  assert outer.namelist()==['Images.zip'], outer.namelist()
  assert outer.getinfo('Images.zip').flag_bits & 1
  try: outer.read('Images.zip')
  except RuntimeError: pass
  else: raise AssertionError('Payload readable without password')
  with zipfile.ZipFile(io.BytesIO(outer.read('Images.zip',pwd=b'synthetic-password'))) as inner:
   assert inner.read('source 5/image.txt',pwd=b'synthetic-password')==b'synthetic archive bytes'
 print('PASS: email exposes only generic entry; two-stage extraction preserves original names/bytes; failed retry preserves destination')
 assert not list((p/'files').glob('.horos-zip-*')), 'Staging directory leaked'
 print('PASS: atomic replacement preserves old destinations on failure and cleans staging')
 print('PASS: plain and password-protected archive entries match source bytes')
