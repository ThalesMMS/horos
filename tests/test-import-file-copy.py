#!/usr/bin/env python3
"""Exercise production import staging against partial writes and collisions."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
program=r'''
#import "HorosFileCopy.h"
@interface PartialCopy:NSFileManager
@end
@implementation PartialCopy
- (BOOL)copyItemAtPath:(NSString*)source toPath:(NSString*)destination error:(NSError**)error {
 [@"partial" writeToFile:destination atomically:NO encoding:NSUTF8StringEncoding error:NULL];
 if(error)*error=[NSError errorWithDomain:NSCocoaErrorDomain code:NSFileReadNoPermissionError userInfo:nil];
 return NO;
}
@end
int main(int argc,char **argv) { @autoreleasepool {
 NSString *directory=[NSString stringWithUTF8String:argv[1]];
 NSString *source=[directory stringByAppendingPathComponent:@"source.dcm"];
 NSString *destination=[directory stringByAppendingPathComponent:@"destination.dcm"];
 [@"original synthetic bytes" writeToFile:source atomically:YES encoding:NSUTF8StringEncoding error:NULL];
 NSData *original=[NSData dataWithContentsOfFile:source];
 NSFileManager *manager=NSFileManager.defaultManager;
 NSError *error=nil;
 NSCAssert(!HorosCopyFileForPublication([[[PartialCopy alloc] init] autorelease],source,destination,NO,&error),@"Partial copy must fail");
 NSCAssert(error.code==NSFileReadNoPermissionError,@"Preserve copy error");
 NSCAssert(error.userInfo[NSUnderlyingErrorKey]!=nil,@"Retain original diagnostic");
 NSCAssert(![error.localizedDescription containsString:@".horos-copy-"],@"Do not expose staging paths in user-facing errors");
 NSCAssert(![manager fileExistsAtPath:destination],@"Never publish partial file");
 NSCAssert([[NSData dataWithContentsOfFile:source] isEqual:original],@"Preserve original");
 for(NSNumber *mounted in @[@NO,@YES]) {
  NSCAssert(HorosCopyFileForPublication(manager,source,destination,mounted.boolValue,&error),@"Complete copy should publish: %@",error);
  NSCAssert([[NSData dataWithContentsOfFile:destination] isEqual:original],@"Exact completed bytes");
  NSCAssert(!HorosCopyFileForPublication(manager,source,destination,mounted.boolValue,&error),@"Existing destination must not be replaced");
  NSCAssert([[NSData dataWithContentsOfFile:destination] isEqual:original],@"Preserve destination after collision");
  [manager removeItemAtPath:destination error:NULL];
  NSCAssert(!HorosCopyFileForPublication(manager,[directory stringByAppendingPathComponent:@"missing.dcm"],destination,mounted.boolValue,&error),@"Missing source must fail");
  NSCAssert(![manager fileExistsAtPath:destination],@"Failed cp must not publish");
 }
 NSArray *remaining=[manager contentsOfDirectoryAtPath:directory error:NULL];
 NSCAssert(remaining.count==1 && [remaining containsObject:@"source.dcm"],@"Remove only owned staging folders");
 puts("PASS: partial copy, successful Foundation/cp copies, collision, missing source, source integrity and staging cleanup");
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-import-copy-') as directory:
 p=Path(directory);(p/'data').mkdir();(p/'test.m').write_text(program)
 subprocess.run(['xcrun','clang','-framework','Foundation','-fsanitize=address','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test'),str(p/'data')],check=True,timeout=20)
