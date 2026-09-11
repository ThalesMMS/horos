#!/usr/bin/env python3
"""Execute actual patient-path construction; empty filtered names must remain children."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':Horos/Sources/BrowserController.m'])
          if len(sys.argv) > 1 else (root / 'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a = source.index('+ (NSMutableString*) replaceNotAdmitted:')
sanitizer = source[a:source.index('\n#ifndef OSIRIX_LIGHT', a)]
a = source.index('                NSString *tempPath', source.index('- (NSArray*) exportDICOMFileInt: (NSMutableDictionary*) parameters'))
block = source[a:source.index('                @synchronized( parameters)', a)]
helper = source[source.index('+ (NSString*) dicomExportPatientFolderName:'):source.index('- (BOOL) confirmDICOMExportFolder:')] if '+ (NSString*) dicomExportPatientFolderName:' in source else ''
program = r'''
#import <Foundation/Foundation.h>
@interface NSString(Range)
- (NSRange)range;
@end
@implementation NSString(Range)
- (NSRange)range { return NSMakeRange(0,self.length); }
@end
@interface BrowserController:NSObject
+ (NSMutableString*)replaceNotAdmitted:(NSString*)name preserveHyphens:(BOOL)preserveHyphens;
+ (NSString*)path:(NSString*)path name:(id)name dicomdir:(BOOL)addDICOMDIR;
+ (NSString*)configuredPatientFolderForImage:(id)image naming:(id)naming;
@end
@implementation BrowserController
+ (NSString*)configuredPatientFolderForImage:(id)image naming:(id)naming { abort(); }
SANITIZER
HELPER
+ (NSString*)path:(NSString*)path name:(id)input dicomdir:(BOOL)addDICOMDIR {
 id customFolderNaming=nil; // Exercise the unchanged default path.
 NSDictionary *study=input==[NSNull null]?@{}:@{@"name":input};
 NSDictionary *curImage=@{@"series":@{@"study":study}};
 BLOCK
 return tempPath;
}
@end
int main(int argc,char **argv) { @autoreleasepool {
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 NSArray *names=@[@"",[NSNull null],@":",@"/",@"\\",@".",@"..",@".,^/\\|:*<>?#%",@"--------",@"Chr-P03R",@"Chr_P03R",@"??AB",@"日本語"];
 for(int mode=0;mode<2;mode++) {
  for(id name in names) {
   NSString *path=[BrowserController path:root name:name dicomdir:mode];
   if(![[path stringByDeletingLastPathComponent] isEqual:root] || [[path lastPathComponent] length]==0) {
    fprintf(stderr,"FAIL mode %d name %s escaped child directory: %s\n",mode,[[name description] UTF8String],[path UTF8String]);return 1;
   }
   if(mode && ![[path lastPathComponent] isEqual:[[path lastPathComponent] uppercaseString]]) { fputs("FAIL lowercase DICOMDIR fallback\n",stderr);return 1; }
  }
  NSString *empty=[BrowserController path:root name:@":*?" dicomdir:mode];
  if(![[empty lastPathComponent] isEqual:mode?@"UNNAMED":@"unnamed"])return 1;
 }
 puts("PASS: 26 real patient-path cases remain child directories; empty names get ordinary/DICOMDIR fallback");
}}
'''.replace('SANITIZER', sanitizer).replace('BLOCK', block).replace('HELPER', helper)
with tempfile.TemporaryDirectory(prefix='horos-patient-component-') as temporary:
    path = Path(temporary)
    (path / 'test.m').write_text(program)
    subprocess.run(['xcrun','clang','-fsanitize=address',str(path/'test.m'),'-framework','Foundation','-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test'),str(path/'exports')],check=True)
