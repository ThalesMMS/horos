#!/usr/bin/env python3
"""Execute actual study/series folder collision blocks with controlled dialog answers."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':Horos/Sources/BrowserController.m'])
          if len(sys.argv) > 1 else (root / 'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
helper = ''
if '- (BOOL) confirmDICOMExportFolder:' in source:
    helper = source[source.index('- (BOOL) confirmDICOMExportFolder:'):source.index('- (NSArray*) exportDICOMFileInt: (NSMutableDictionary*) parameters')]
for level, marker in [('study', 'DICOM-STUDY'), ('series', 'DICOM-SERIE')]:
    start = source.index('                    // Confirm distinct ' + level) if '                    // Confirm distinct ' + level in source else source.index('                    // Find the ' + marker + ' folder')
    end_marker = '\n                    studyPath = tempPath;' if level == 'study' else '\n                }\n                else studyPath = tempPath;'
    end = source.index(end_marker, start)
    block = source[start:end]
    # The series block consumes the identity established by the enclosing study block.
    outer_identity = 'id studyIdentity = request[@"parent"];' if level == 'series' else ''
    program = r'''
#import <Cocoa/Cocoa.h>
@interface Peer : NSObject { @public int answer, prompts, completed; BOOL exportAborted; NSError *exportError; }
- (void)run:(NSArray*)requests;
@end
@implementation Peer
- (void)runInformationAlertPanel:(NSMutableDictionary*)options { prompts++; options[@"result"]=@(answer); }
HELPER
- (void)run:(NSArray*)requests {
 NSMutableDictionary *reviewedStudyFolders=[NSMutableDictionary dictionary];
 NSMutableDictionary *reviewedSeriesFolders=[NSMutableDictionary dictionary];
 for(NSDictionary *request in requests) {
  NSString *tempPath=request[@"path"];
  id patientIdentity=request[@"parent"];
  OUTER
  NSDictionary *curImage=@{@"series":@{@"seriesInstanceUID":request[@"uid"],@"study":@{@"studyInstanceUID":request[@"uid"]}}};
  BODY
  completed++;
 }
}
@end
int main(int argc, char **argv) { @autoreleasepool {
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 for(int scenario=0;scenario<5;scenario++) {
  NSString *path=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"%d",scenario]];
  Peer *peer=[Peer new];peer->answer=scenario==1?NSAlertAlternateReturn:(scenario==2?NSAlertDefaultReturn:NSAlertOtherReturn);
  [[NSFileManager defaultManager] createDirectoryAtPath:path withIntermediateDirectories:YES attributes:nil error:NULL];
  NSString *sentinel=[path stringByAppendingPathComponent:@"existing.txt"];
  [@"preserve" writeToFile:sentinel atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  NSDictionary *a=@{@"path":path,@"parent":@"parent",@"uid":@"A"};
  NSDictionary *b=@{@"path":scenario==3?[path stringByAppendingString:@"-distinct"]:path,@"parent":scenario==4?@"other-parent":@"parent",@"uid":@"B"};
  [peer run:@[a,a,b]];
  int expectedPrompts=scenario>=3?0:1;
  if(peer->prompts!=expectedPrompts || peer->completed!=(scenario==1?2:3) || peer->exportAborted!=(scenario==1)) {
   fprintf(stderr,"FAIL scenario %d: prompts %d expected %d, completed %d aborted %d\n",scenario,peer->prompts,expectedPrompts,peer->completed,peer->exportAborted);return 1;
  }
  if([[NSFileManager defaultManager] fileExistsAtPath:sentinel]!=(scenario!=2)) { fputs("FAIL sentinel contents\n",stderr);return 1; }
  [peer release];
 }
 puts("PASS: hierarchy Merge, Cancel, Replace, distinct paths and parent identities");
}}
'''.replace('HELPER', helper).replace('OUTER', outer_identity).replace('BODY', block)
    with tempfile.TemporaryDirectory(prefix='horos-' + level + '-collision-') as temporary:
        path = Path(temporary)
        (path / 'test.m').write_text(program)
        subprocess.run(['xcrun', 'clang', '-fsanitize=address', '-Wno-deprecated-declarations', str(path / 'test.m'), '-framework', 'Cocoa', '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test'), str(path / 'exports')], check=True)
        print(level + ': passed')
