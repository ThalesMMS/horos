#!/usr/bin/env python3
"""Exercise viewer's actual write guard and AppleEvent attachment loop."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
a=s.index('if( ![bitmapData writeToFile:jpegFile atomically:YES])')
b=s.index('\n                        NSManagedObject',a)
write=s[a:b]
a=s.index('NSArray *files = mailExportFiles;')
b=s.index('NSString *mailError = [HorosMailDraftComposer',a)
loop=s[a:b]
code=r'''
#import <Cocoa/Cocoa.h>
int main(int argc,char **argv){@autoreleasepool{
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 NSFileManager *fm=NSFileManager.defaultManager;
 for(int scenario=0;scenario<3;scenario++) {
  NSMutableArray *mailExportFiles=[NSMutableArray array];
  BOOL sharedImageExportFailed=NO;
  // Intentionally non-lexical order: the attachment list must retain generation order.
  NSArray *names=@[@"0003.jpg",@"0001.jpg",@"0002.jpg"];
  for(int i=0;i<3;i++) {
   NSString *jpegFile=[root stringByAppendingPathComponent:names[i]];
   NSData *bitmapData=[@"synthetic image output" dataUsingEncoding:NSUTF8StringEncoding];
   if(scenario==1 && i==1)jpegFile=[root stringByAppendingPathComponent:@"missing/0001.jpg"];
   if(scenario==2 && i==0)bitmapData=nil;
   WRITE
  }
  if(sharedImageExportFailed!=(scenario!=0))return 1;
  if(mailExportFiles.count!=(scenario==0?3:scenario==1?1:0))return 2;
  if(sharedImageExportFailed || !mailExportFiles.count)continue;
  LOOP
  if(mailFilePaths.count!=3)return 3;
  for(int i=0;i<3;i++)if(![[[mailFilePaths objectAtIndex:i] lastPathComponent] isEqual:names[i]])return 4;
 }
 puts("PASS: attachment path order; failed and nil writes stop collection; empty/partial handoff suppressed");
}}
'''.replace('WRITE',write).replace('LOOP',loop)
assert 'tag] == 3 && !sharedImageExportFailed && mailExportFiles.count > 0)' in s
assert 'HorosMailDraftComposer' in s
assert 'defaultaddress@mac.com' not in s
with tempfile.TemporaryDirectory(prefix='horos-mail-files-') as d:
 p=Path(d);(p/'main.m').write_text(code)
 subprocess.run(['xcrun','clang','-fsanitize=address','-framework','Cocoa',str(p/'main.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),d],check=True)
