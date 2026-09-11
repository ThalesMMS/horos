#!/usr/bin/env python3
"""Run the actual export copy block against real success/failure filesystem paths."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(__file__).resolve().parents[1]
s=(subprocess.check_output(['git','show',sys.argv[1]+':Horos/Sources/BrowserController.m']) if len(sys.argv)>1 else (root/'Horos/Sources/BrowserController.m').read_bytes()).decode('latin1')
a=s.index('                NSError *error = nil;',s.index('- (NSArray*) exportDICOMFileInt: (NSMutableDictionary*) parameters'))
b=s.index('                if( [[curImage valueForKey: @"fileType"] hasPrefix:@"DICOM"])',a)
block=s[a:b]
# Current source schedules collision renaming only after successful copy. Include
# the required locals and verify failed copies schedule no rename operation.
program=r'''
#import <Foundation/Foundation.h>
#import "HorosFileCopy.h"
int main(int argc,char **argv) { @autoreleasepool {
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 [[NSFileManager defaultManager] createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:NULL];
 NSString *source=[root stringByAppendingPathComponent:@"source"];
 [@"original bytes" writeToFile:source atomically:YES encoding:NSUTF8StringEncoding error:NULL];
 for(int scenario=0;scenario<5;scenario++) {
  NSArray *filesToExport=@[(scenario==1 || scenario==4)?[root stringByAppendingPathComponent:@"missing"]:source];
  NSString *dest=scenario==2?nil:[root stringByAppendingPathComponent:[NSString stringWithFormat:@"output-%d",scenario]];
  if(scenario==3)dest=[source stringByAppendingPathComponent:@"child"];
  NSError *exportError=nil;BOOL exportAborted=NO;int completed=0;
  NSMutableSet *exportedPaths=[NSMutableSet set];
  NSMutableArray *renameArray=[NSMutableArray array];
  int t=scenario==4?3:2,serieCount=1,imageNo=1;BOOL addDICOMDIR=NO;NSString *tempPath=root,*extension=@"dcm";
  for(NSUInteger i=0;i<filesToExport.count;i++) {
   BODY
   completed++;
  }
  if(scenario==0) {
   if(exportAborted || exportError || completed!=1 || ![[NSData dataWithContentsOfFile:source] isEqual:[NSData dataWithContentsOfFile:dest]])return 1;
  } else if(!exportAborted || !exportError || !exportError.localizedDescription.length || completed || renameArray.count) {
   fprintf(stderr,"FAIL scenario %d: aborted %d error %s continued %d\n",scenario,exportAborted,[[exportError description] UTF8String],completed);return 1;
  }
 }
 puts("PASS: copy success preserved; missing source, nil destination and invalid parent stop with actionable errors");
}}
'''.replace('BODY',block)
with tempfile.TemporaryDirectory(prefix='horos-copy-failure-') as folder:
 p=Path(folder);(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-I',str(root/'Horos/Sources'),'-fsanitize=address',str(p/'test.m'),'-framework','Foundation','-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'files')],check=True)
