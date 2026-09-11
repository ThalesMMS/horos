#!/usr/bin/env python3
"""Run actual patient-folder handling with real temporary folders and controlled answers."""
from pathlib import Path
import subprocess,tempfile,sys
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('                // Track the source patient') if '                // Track the source patient' in s else s.index('                // Find the DICOM-PATIENT folder')
b=s.index('                NSString *studyPath = nil;',a)
helper = s[s.index('- (BOOL) confirmDICOMExportFolder:'):s.index('- (NSArray*) exportDICOMFileInt: (NSMutableDictionary*) parameters')] if '- (BOOL) confirmDICOMExportFolder:' in s else ''
code=r'''
#import <Cocoa/Cocoa.h>
@interface Peer:NSObject { @public NSInteger prompts,answer,completed; BOOL exportAborted; NSError *exportError; }
- (void)runInformationAlertPanel:(NSMutableDictionary*)options;
- (void)run:(NSArray*)requests;
@end
@implementation Peer
HELPER
- (void)runInformationAlertPanel:(NSMutableDictionary*)options {prompts++;options[@"result"]=@(answer);}
- (void)run:(NSArray*)requests {
 NSMutableSet *reviewedPatientFolders=[NSMutableSet set];
 for(NSUInteger i=0;i<requests.count;i++) {
  NSDictionary *request=requests[i];NSString *tempPath=request[@"path"];
  NSDictionary *curImage=@{@"series":@{@"study":@{@"patientUID":request[@"patient"]}}};
BODY
  completed++;
 }
}
@end
int main(int argc,char **argv){@autoreleasepool{
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 for(int scenario=0;scenario<5;scenario++) {
  NSString *path=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"%d",scenario]];
  Peer *peer=[Peer new];peer->answer=scenario==2?NSAlertAlternateReturn:(scenario==4?NSAlertDefaultReturn:NSAlertOtherReturn);
  NSDictionary *a=@{@"path":path,@"patient":@"A"};NSDictionary *b=@{@"path":path,@"patient":@"B"};
  if(scenario==1 || scenario==4)[[NSFileManager defaultManager] createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL];
  NSString *sentinel=[path stringByAppendingPathComponent:@"existing.txt"];
  if(scenario==1 || scenario==4)[@"preserve" writeToFile:sentinel atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  if(scenario==3) {
   NSString *later=[path stringByAppendingString:@"-later"];
   [[NSFileManager defaultManager] createDirectoryAtPath:later withIntermediateDirectories:YES attributes:nil error:NULL];
   b=@{@"path":later,@"patient":@"B"};
  }
  [peer run:@[a,a,b]];
  if((scenario==1 && ![[NSFileManager defaultManager] fileExistsAtPath:sentinel]) ||
     (scenario==4 && [[NSFileManager defaultManager] fileExistsAtPath:sentinel])) {
   fprintf(stderr,"FAIL existing contents after merge/replace\n");return 1;
  }
  NSInteger expectedPrompts=(scenario==1 || scenario==4)?2:1;
  if(peer->prompts!=expectedPrompts || peer->completed!=(scenario==2?2:3) || peer->exportAborted!=(scenario==2)) {
   fprintf(stderr,"FAIL scenario %d: prompts %ld expected %ld, completed %ld aborted %d\n",scenario,(long)peer->prompts,(long)expectedPrompts,(long)peer->completed,peer->exportAborted);return 1;
  }
  [peer release];
 }
 puts("PASS: later patient collision prompts, repeated images do not; pre-existing destinations prompt per patient; cancellation stops the batch");
}}
'''.replace('BODY',s[a:b]).replace('HELPER',helper)
with tempfile.TemporaryDirectory(prefix='horos-folder-confirm-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=address','-Wno-deprecated-declarations',str(p/'test.m'),'-framework','Cocoa','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'exports')],check=True)
