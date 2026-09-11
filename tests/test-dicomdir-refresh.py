#!/usr/bin/env python3
"""Execute the exporter's real DICOMDIR scheduling against existing index paths."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('        if (addDICOMDIR && exportAborted == NO)');b=s.index('\n#endif',a)
code=r'''
#import <Foundation/Foundation.h>
typedef NSDictionary NSManagedObject;
static int attempts,fail;
@interface NSThread(Status)
@property(copy) NSString *status;
@end
@implementation NSThread(Status)
- (void)setStatus:(NSString*)status{}
- (NSString*)status{return @"";}
@end
@interface DicomDir:NSObject
+ (BOOL)createDicomDirAtDir:(NSString*)path error:(NSError**)error;
@end
@implementation DicomDir
+ (BOOL)createDicomDirAtDir:(NSString*)path error:(NSError**)error {attempts++;if(fail)*error=[NSError errorWithDomain:@"test" code:1 userInfo:nil];return !fail;}
@end
@interface BrowserController:NSObject
+ (NSString*)dicomExportPatientFolderName:(NSString*)name addDICOMDIR:(BOOL)flag;
+ (NSString*)configuredPatientFolderForImage:(NSManagedObject*)image naming:(id)naming;
@end
@implementation BrowserController
+ (NSString*)dicomExportPatientFolderName:(NSString*)name addDICOMDIR:(BOOL)flag{return name;}
// The exporter gained an optional naming scheme; with none configured it must
// keep folding a patient's images into one folder, which is what this measures.
+ (NSString*)configuredPatientFolderForImage:(NSManagedObject*)image naming:(id)naming{
 return [image valueForKeyPath:@"series.study.name"];}
@end
@interface Peer:NSObject { @public int alerts; }
- (BOOL)run:(NSString*)path enabled:(BOOL)addDICOMDIR naming:(id)naming;
@end
@implementation Peer
- (void)showDICOMExportError:(NSError*)error{alerts++;}
- (BOOL)run:(NSString*)path enabled:(BOOL)addDICOMDIR naming:(id)naming {
 BOOL exportAborted=NO;
 NSArray *filesToExport=@[@1,@2,@3];
 NSDictionary *a=@{@"series":@{@"study":@{@"name":@"A"}}};
 NSDictionary *b=@{@"series":@{@"study":@{@"name":@"B"}}};
 NSArray *dicomFiles2Export=@[a,a,b];
 id customFolderNaming = naming;
 BODY
 return exportAborted;
}
@end
int main(int argc,char **argv){@autoreleasepool{
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 for(NSString *name in @[@"A",@"B"]) {
  NSString *folder=[root stringByAppendingPathComponent:name];
  [[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:NULL];
  [@"existing index" writeToFile:[folder stringByAppendingPathComponent:@"DICOMDIR"] atomically:YES encoding:NSUTF8StringEncoding error:NULL];
 }
 for(int scenario=0;scenario<3;scenario++) {
  attempts=0;fail=scenario==1;Peer *p=[Peer new];
  BOOL aborted=[p run:root enabled:scenario!=2 naming:nil];
  int expected=scenario==0?2:(scenario==1?1:0);
  if(attempts!=expected || aborted!=(scenario==1) || p->alerts!=(scenario==1)) {fprintf(stderr,"FAIL scenario %d attempts %d expected %d aborted %d\n",scenario,attempts,expected,aborted);return 1;}[p release];
 }
 puts("PASS: existing DICOMDIR rebuilt once per patient; failure stops; disabled option skips indexing");
}}
'''.replace('BODY',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-dicomdir-refresh-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'files')],check=True)
