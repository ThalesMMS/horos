#!/usr/bin/env python3
"""Run actual export rename stage with real filesystem collisions."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('        [[DicomStudy dbModifyLock] unlock];',s.index('- (NSArray*) exportDICOMFileInt:'))
a=s.index('\n',a)+1;b=s.index('        //close progress window',a)
program=r'''
#import <Foundation/Foundation.h>
int main(int argc,char **argv){@autoreleasepool{
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 for(int scenario=0;scenario<5;scenario++){
  NSString *folder=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"%d",scenario]];
  [[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:NULL];
  NSString *oldName=[folder stringByAppendingPathComponent:@"old.dcm"],*newName=[folder stringByAppendingPathComponent:@"new.dcm"];
  if(scenario!=3)[@"source bytes" writeToFile:oldName atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  if(scenario==2 || scenario==4)[@"existing bytes" writeToFile:newName atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  NSDictionary *rename=@{@"oldName":oldName,@"newName":newName};
  NSMutableSet *exportedPaths=[NSMutableSet set];
  NSArray *renameArray=scenario==1?@[rename,rename,rename]:@[rename];
  NSMutableArray *files2Compress=[NSMutableArray arrayWithObjects:oldName,@"another file",nil];
  NSError *originalError=scenario==4?[NSError errorWithDomain:@"prior" code:1 userInfo:nil]:nil;
  NSError *exportError=originalError;BOOL exportAborted=NO;
  BODY
  if(scenario<2){
   if(exportAborted || exportError || ![[files2Compress objectAtIndex:0] isEqual:newName] || [[NSFileManager defaultManager] fileExistsAtPath:oldName])return 1;
   if(![[NSString stringWithContentsOfFile:newName encoding:NSUTF8StringEncoding error:NULL] isEqual:@"source bytes"])return 2;
  }else{
   if(!exportAborted || !exportError || ![[files2Compress objectAtIndex:0] isEqual:oldName])return 3;
   if(scenario==4 && exportError!=originalError)return 4;
   if(scenario!=3 && ![[NSString stringWithContentsOfFile:newName encoding:NSUTF8StringEncoding error:NULL] isEqual:@"existing bytes"])return 6;
   if(scenario!=3 && ![[NSString stringWithContentsOfFile:oldName encoding:NSUTF8StringEncoding error:NULL] isEqual:@"source bytes"])return 5;
  }
 }
 puts("PASS: rename updates codec paths, handles duplicate requests and reports failures preserving sources");
}}
'''.replace('BODY',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-export-rename-') as folder:
 p=Path(folder);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address',str(p/'test.m'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'files')],check=True)
