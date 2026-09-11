#!/usr/bin/env python3
"""Execute the viewer's real per-export directory creation block twice."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'Horos/Sources/ViewerController.m').read_bytes().decode('latin1')
a=s.index('            NSString *sharedExportRoot =');b=s.index('            NSMutableArray *mailExportFiles',a)
code=r'''
#import <Cocoa/Cocoa.h>
static NSString *testRoot;
static NSMutableArray *created;
@interface BrowserController:NSObject
+ (id)currentBrowser;
- (id)database;
- (NSString*)tempDirPath;
@end
@implementation BrowserController
+ (id)currentBrowser {return [[[self alloc] init] autorelease];}
- (id)database {return self;}
- (NSString*)tempDirPath {return testRoot;}
@end
static void prepare(void) {
BODY
 [created addObject:sharedExportRoot];
}
int main(int argc,char **argv){@autoreleasepool{
 testRoot=[NSString stringWithUTF8String:argv[1]];
 created=[NSMutableArray array];
 prepare();
 NSString *first=[created[0] stringByAppendingPathComponent:@"0001.jpg"];
 [@"first draft bytes" writeToFile:first atomically:YES encoding:NSUTF8StringEncoding error:NULL];
 prepare();
 if(created.count!=2 || [created[0] isEqual:created[1]])return 1;
 if(![[NSString stringWithContentsOfFile:first encoding:NSUTF8StringEncoding error:NULL] isEqual:@"first draft bytes"])return 2;
 for(NSString *path in created) {
  NSNumber *mode=[[NSFileManager.defaultManager attributesOfItemAtPath:path error:NULL] objectForKey:NSFilePosixPermissions];
  if(mode.intValue!=0700)return 3;
 }
 puts("PASS: independent private export directories preserve earlier draft bytes");
}}
'''.replace('BODY',s[a:b])
with tempfile.TemporaryDirectory(prefix='horos-export-directory-') as d:
 p=Path(d);(p/'main.m').write_text(code)
 subprocess.run(['xcrun','clang','-Wno-deprecated-declarations','-fsanitize=address','-framework','Cocoa',str(p/'main.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),d],check=True)
