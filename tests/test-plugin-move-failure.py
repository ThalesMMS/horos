#!/usr/bin/env python3
"""Exercise the real plugin move helper with controlled authorization outcomes."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root / 'Horos/Sources/PluginManager.m').read_bytes().decode('latin1')
start = source.index('+ (void)movePluginFromPath:')
method = source[start:source.index('\n}', start) + 2]
program = r'''
#import <Foundation/Foundation.h>
static BOOL denyMove;
static int alerts, copies;
static NSInteger NSRunCriticalAlertPanel(NSString *title, NSString *message, NSString *button, id alternate, id other, ...) { alerts++; return 1; }
@interface BLAuthentication:NSObject
+ (id)sharedInstance;
- (BOOL)executeCommand:(NSString*)command withArgs:(NSArray*)args;
@end
@implementation BLAuthentication
+ (id)sharedInstance { static id instance; if(!instance) instance=[self new]; return instance; }
- (BOOL)executeCommand:(NSString*)command withArgs:(NSArray*)args {
 NSString *source=args[args.count-2], *destination=args.lastObject;
 if([command isEqual:@"/bin/mv"]) {
  if(denyMove) return NO;
  return [[NSFileManager defaultManager] moveItemAtPath:source toPath:destination error:NULL];
 }
 NSCAssert([command isEqual:@"/bin/cp"],@"Unexpected command");
 copies++;
 return [[NSFileManager defaultManager] copyItemAtPath:source toPath:destination error:NULL];
}
@end
@interface PluginManager:NSObject
+ (void)movePluginFromPath:(NSString*)source toPath:(NSString*)destination;
@end
@implementation PluginManager
METHOD
@end
int main(int argc,char **argv) { @autoreleasepool {
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 NSString *active=[root stringByAppendingPathComponent:@"active/QA.horosplugin"];
 NSString *inactive=[root stringByAppendingPathComponent:@"inactive/QA.horosplugin"];
 NSFileManager *fm=[NSFileManager defaultManager];
 [fm createDirectoryAtPath:active withIntermediateDirectories:YES attributes:nil error:NULL];
 NSData *bytes=[@"synthetic plugin bytes" dataUsingEncoding:NSUTF8StringEncoding];
 [bytes writeToFile:[active stringByAppendingPathComponent:@"payload"] atomically:YES];
 denyMove=YES;
 [PluginManager movePluginFromPath:active toPath:inactive];
 NSCAssert(copies==0,@"Failed move must not become a copy that leaves the plugin active");
 NSCAssert(alerts==1,@"Failed move must be reported");
 NSCAssert([fm fileExistsAtPath:active] && ![fm fileExistsAtPath:inactive],@"Denied move must preserve source without creating a duplicate");
 denyMove=NO;
 [PluginManager movePluginFromPath:active toPath:inactive];
 NSCAssert(![fm fileExistsAtPath:active] && [fm fileExistsAtPath:inactive],@"Successful disable must remove active source");
 NSCAssert([[NSData dataWithContentsOfFile:[inactive stringByAppendingPathComponent:@"payload"]] isEqual:bytes],@"Move must preserve bytes");
 [PluginManager movePluginFromPath:inactive toPath:active];
 NSCAssert([fm fileExistsAtPath:active] && ![fm fileExistsAtPath:inactive] && alerts==1,@"Reactivation must move back without errors");
 puts("PASS: denied move is reported without copying; disable and reactivation preserve bytes");
} }
'''.replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-plugin-move-') as directory:
    p = Path(directory)
    (p/'test.m').write_text(program)
    subprocess.run(['xcrun','clang','-framework','Foundation','-fsanitize=address',str(p/'test.m'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test'),str(p/'data')],check=True,timeout=30)
