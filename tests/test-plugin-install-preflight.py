#!/usr/bin/env python3
"""Verify rejected updates cannot reach deletion of the installed plugin."""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=root/'Horos/Sources/PluginManager.m')
args = parser.parse_args()
source = args.source.read_bytes().decode('latin1')
start = source.index('+ (void) installPluginFromPath:')
method = source[start:source.index('\n}', start)+2]
program = r'''
#import <Foundation/Foundation.h>
#import "HorosPluginSignature.h"
static int deletions, moves, alerts;
static BOOL duplicateInstallations, inactiveInstallation;
static NSString *installRoot, *lastDestination;
static BOOL HorosInstallPlugin(NSString *source, NSString *destination, NSError **error) { moves++; lastDestination=destination; return YES; }
static NSInteger NSRunCriticalAlertPanel(NSString *title, NSString *message, NSString *button, id alternate, id other, ...) { alerts++; return 1; }
@interface HorosArchitectureAudit:NSObject
+ (NSString*)pluginDiagnosisAtPath:(NSString*)path;
@end
@implementation HorosArchitectureAudit
+ (NSString*)pluginDiagnosisAtPath:(NSString*)path {
    if ([path rangeOfString:@"QAIntel"].location != NSNotFound)
        return @"This plugin is Intel-only (x86_64) and cannot load in this arm64 Horos process. Obtain an arm64 plugin from its author.";
    return nil;
}
@end
@interface PluginManager:NSObject
+ (void)installPluginFromPath:(NSString*)path;
+ (BOOL)isPluginBundleSignatureValid:(NSString*)path;
+ (NSArray*)pluginsList;
+ (NSArray*)availabilities;
+ (void)deletePluginWithName:(NSString*)name;
+ (void)movePluginFromPath:(NSString*)source toPath:(NSString*)destination;
DIRECTORY_DECLARATIONS
@end
@implementation PluginManager
+ (BOOL)isPluginBundleSignatureValid:(NSString*)path { return HorosPluginSignatureAllowsLoading(path,NULL); }
+ (NSArray*)pluginsList { return duplicateInstallations ? @[@{@"name":@"QAUniversal",@"availability":@"User",@"active":@YES},@{@"name":@"QAUniversal",@"availability":@"App",@"active":@YES}] : (inactiveInstallation ? @[@{@"name":@"QAUniversal",@"availability":@"User",@"active":@NO}] : @[]); }
+ (NSArray*)availabilities { return @[@"User",@"System",@"App"]; }
+ (void)deletePluginWithName:(NSString*)name { deletions++; }
+ (void)movePluginFromPath:(NSString*)source toPath:(NSString*)destination { moves++; }
DIRECTORY_METHODS
METHOD
@end
int main(int argc,char **argv) { @autoreleasepool {
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 installRoot=root;
 NSMutableArray *rejected=[NSMutableArray arrayWithArray:@[@"Missing",@"QAInvalidSignature"]];
#if defined(__arm64__)
 [rejected addObject:@"QAIntel"];
#endif
 for(NSString *name in rejected) {
  [PluginManager installPluginFromPath:[root stringByAppendingPathComponent:[name stringByAppendingString:@".horosplugin"]]];
  NSCAssert(deletions==0 && moves==0,@"Rejected update must preserve installed plugin: %@",name);
 }
 NSCAssert(alerts==rejected.count,@"Each rejection must explain the failure");
 [PluginManager installPluginFromPath:[root stringByAppendingPathComponent:@"QAUniversal.horosplugin"]];
 NSCAssert(deletions==0 && moves==1,@"Compatible candidate must reach existing install flow");
 inactiveInstallation=YES;
 NSString *legacy=[[PluginManager userInactivePluginsDirectoryPath] stringByAppendingPathComponent:@"QAUniversal.osirixplugin"];
 [[NSFileManager defaultManager] createDirectoryAtPath:legacy withIntermediateDirectories:YES attributes:nil error:NULL];
 [PluginManager installPluginFromPath:[root stringByAppendingPathComponent:@"QAUniversal.horosplugin"]];
 NSCAssert(moves==2 && [lastDestination isEqual:legacy],@"Update must preserve inactive location and legacy extension");
 duplicateInstallations=YES;
 [PluginManager installPluginFromPath:[root stringByAppendingPathComponent:@"QAUniversal.horosplugin"]];
 NSCAssert(deletions==0 && moves==2 && alerts==rejected.count+1,@"Ambiguous duplicates must be preserved without installing");
 NSCAssert(NSClassFromString(@"QAUniversal")==Nil,@"Preflight must not execute candidate code");
 puts("PASS: missing, invalid-signature and incompatible updates rejected before deletion; compatible preflight does not load code");
} }
'''
names=[f'{scope}{state}PluginsDirectoryPath' for scope in ('user','system','app') for state in ('Active','Inactive')]
program=program.replace('DIRECTORY_DECLARATIONS','\n'.join(f'+ (NSString*){n};' for n in names)).replace('DIRECTORY_METHODS','\n'.join(f'+ (NSString*){n} {{ return [installRoot stringByAppendingPathComponent:@"{n}"]; }}' for n in names)).replace('METHOD',method)
with tempfile.TemporaryDirectory(prefix='horos-install-preflight-') as directory:
    p=Path(directory)
    subprocess.run(['python3',str(root/'tools/generate-plugin-load-fixtures.py'),str(p/'fixtures')],check=True)
    (p/'test.m').write_text(program)
    subprocess.run(['xcrun','clang','-framework','Foundation','-framework','Security','-fsanitize=address','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test'),str(p/'fixtures')],check=True,timeout=30)
