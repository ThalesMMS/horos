#!/usr/bin/env python3
"""Run each production export folder creation guard with a non-directory parent."""
from pathlib import Path
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
source=(root/'Horos/Sources/BrowserController.m').read_bytes().decode('latin1')
start=source.index('- (NSArray*) exportDICOMFileInt: (NSMutableDictionary*) parameters')
blocks=re.findall(r'if \(!\[\[NSFileManager defaultManager\] createDirectoryAtPath:tempPath[^\n]+\{\n\s+exportAborted = YES;\n\s+break;\n\s+\}',source[start:])
assert len(blocks)==3, 'Patient, study and series creation must propagate failure'
with tempfile.TemporaryDirectory(prefix='horos-export-folder-') as directory:
 p=Path(directory)
 methods=[]
 for index,block in enumerate(blocks):
  methods.append('int guard%d(NSString *tempPath) { NSError *exportError=nil; BOOL exportAborted=NO; int continued=0; for(int once=0;once<1;once++) { %s continued++; } return exportAborted && exportError && !continued; }'%(index,block))
 program='#import <Foundation/Foundation.h>\n'+'\n'.join(methods)+r'''
int main(int argc,char **argv) { @autoreleasepool {
 NSString *path=[NSString stringWithUTF8String:argv[1]];
 [@"preserved" writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:NULL];
 NSString *child=[path stringByAppendingPathComponent:@"child"];
 NSCAssert(guard0(child)&&guard1(child)&&guard2(child),@"All hierarchy levels must stop on original mkdir failure");
 NSCAssert([[NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:NULL] isEqual:@"preserved"],@"Preserve existing file");
 puts("PASS: patient/study/series folder errors stop export and preserve existing data");
} }
'''
 (p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-fsanitize=address','-framework','Foundation',str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'parent-file')],check=True)
