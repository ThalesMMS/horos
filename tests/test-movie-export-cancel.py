#!/usr/bin/env python3
"""Run the actual post-panel file-handling block against a retained destination."""
from pathlib import Path
import subprocess, tempfile, sys
root=Path(__file__).resolve().parents[1]
source=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/QuicktimeExport.m']) if len(sys.argv)>1 else (root/'Horos/Sources/QuicktimeExport.m').read_bytes()).decode('utf-8')
a=source.index('        fileName = panel.URL.path;')+len('        fileName = panel.URL.path;')
a=source.index('    }',a)+len('    }')
b=source.index('    @try',a)
body=source[a:b]
code=r'''
#import <Cocoa/Cocoa.h>
@interface NSFileManager(TestTrash)
- (void)moveItemAtPathToTrash:(NSString*)path;
@end
@implementation NSFileManager(TestTrash)
- (void)moveItemAtPathToTrash:(NSString*)path { abort(); }
@end
static NSString *request(NSString *fileName, NSInteger result) {
BODY
return fileName;
}
int main(int argc,char **argv) { @autoreleasepool {
 NSString *path=[NSString stringWithUTF8String:argv[1]];
 NSData *original=[@"existing movie must survive cancellation" dataUsingEncoding:NSUTF8StringEncoding];
 [original writeToFile:path atomically:YES];
 for(NSNumber *response in @[@(NSModalResponseCancel),@(NSModalResponseAbort),@(NSModalResponseStop)]) {
  NSString *result=request(path,response.integerValue);
  if(result || ![[NSData dataWithContentsOfFile:path] isEqual:original]) {
   fprintf(stderr,"FAIL: rejected save request modified destination or reported success\n");return 1;
  }
 }
 if(![request(path,NSModalResponseOK) isEqual:path] || [[NSFileManager defaultManager] fileExistsAtPath:path]) {
  fprintf(stderr,"FAIL: accepted overwrite did not proceed\n");return 1;
 }
 puts("PASS: Cancel/Abort/Stop preserve existing bytes and return nil; accepted overwrite proceeds");
}}
'''.replace('BODY',body)
with tempfile.TemporaryDirectory(prefix='horos-movie-cancel-') as folder:
 p=Path(folder);(p/'test.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Cocoa','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'existing.mov')],check=True)
