#!/usr/bin/env python3
"""Run the production loader against disposable compiled plugin bundles."""
from pathlib import Path
import platform
import subprocess
import tempfile
root = Path(__file__).resolve().parent.parent
source = (root/'Horos/Sources/PluginManager.m').read_bytes().decode('latin1')
start = source.index('+ (void) loadPluginBundle:(NSString*) path')
method = source[start:source.index('\n}', start)+2]
signature_start = source.index('+ (BOOL) isPluginBundleSignatureValid:')
signature_method = source[signature_start:source.index('\n}', signature_start)+2]
program = r'''
#import <Foundation/Foundation.h>
#import "HorosPluginLoadDiagnostics.h"
#import "HorosPluginSignature.h"
static NSMutableDictionary *pluginsNames, *pluginsBundleDictionnary, *fileFormatPlugins, *plugins, *pluginsDict, *reportPlugins;
static NSMutableArray *preProcessPlugins;
static int protectedDepth;
static BOOL protectedMode;
@interface NSString (Aliases)
- (NSString*)stringByResolvingAlias;
@end
@implementation NSString (Aliases)
- (NSString*)stringByResolvingAlias { return self.stringByResolvingSymlinksInPath; }
@end
@interface PluginFilter:NSObject
+ (id)filter;
@end
@interface T2FitMapCompatibility:NSObject
+ (NSString*)diagnosticForBundleAtPath:(NSString*)path loadErrorDomain:(NSString*)domain loadErrorCode:(NSInteger)code;
@end
@implementation T2FitMapCompatibility
+ (NSString*)diagnosticForBundleAtPath:(NSString*)path loadErrorDomain:(NSString*)domain loadErrorCode:(NSInteger)code { return nil; }
@end
@interface ROIEnhancementCompatibility:NSObject
+ (NSString*)diagnosticForBundleAtPath:(NSString*)path loadErrorDomain:(NSString*)domain loadErrorCode:(NSInteger)code;
@end
@implementation ROIEnhancementCompatibility
+ (NSString*)diagnosticForBundleAtPath:(NSString*)path loadErrorDomain:(NSString*)domain loadErrorCode:(NSInteger)code { return nil; }
@end
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
@interface DCMPix:NSObject
+ (BOOL)isRunOsiriXInProtectedModeActivated;
@end
@implementation DCMPix
+ (BOOL)isRunOsiriXInProtectedModeActivated { return protectedMode; }
@end
@interface PluginManager:NSObject
+ (BOOL)isPluginBundleSignatureValid:(NSString*)path;
+ (void)startProtectForCrashWithPath:(NSString*)path;
+ (void)endProtectForCrash;
+ (void)loadPluginBundle:(NSString*)path;
@end
@implementation PluginManager
SIGNATURE_METHOD
+ (void)startProtectForCrashWithPath:(NSString*)path { protectedDepth++; }
+ (void)endProtectForCrash { protectedDepth--; }
METHOD
@end
int main(int argc,char **argv) { @autoreleasepool {
 pluginsNames=[NSMutableDictionary new]; pluginsBundleDictionnary=[NSMutableDictionary new];
 fileFormatPlugins=[NSMutableDictionary new];plugins=[NSMutableDictionary new];pluginsDict=[NSMutableDictionary new];reportPlugins=[NSMutableDictionary new];preProcessPlugins=[NSMutableArray new];
 NSString *root=[NSString stringWithUTF8String:argv[1]];
 NSString *universalPath=[root stringByAppendingPathComponent:@"QAUniversal.horosplugin"];
 protectedMode=YES;
 [PluginManager loadPluginBundle:universalPath];
 NSCAssert([HorosPluginLoadOutcome(universalPath,YES)[@"loadState"] isEqual:@"Blocked"],@"Protected mode must explain why loading was blocked");
 NSCAssert(NSClassFromString(@"QAUniversal")==Nil,@"Protected mode must prevent executable loading, not just hide its menu");
 NSCAssert(plugins.count==0 && pluginsBundleDictionnary.count==0 && protectedDepth==0,@"Protected mode must not register code or leave a crash marker");
 protectedMode=NO;
 NSArray *names=@[@"QAUniversal",@"QAIntel",@"QAMissingClass",@"QAInitializationFailure",@"QAInvalidSignature"];
 for(NSString *name in names) {
  NSString *path=[root stringByAppendingPathComponent:[name stringByAppendingString:@".horosplugin"]];
  [PluginManager loadPluginBundle:path];
  NSString *state=HorosPluginLoadOutcome(path,YES)[@"loadState"];
  NSString *expected=[name isEqual:@"QAUniversal"]?@"Loaded":([name isEqual:@"QAInitializationFailure"]?@"Load failed":@"Incompatible");
#if defined(__x86_64__)
  if([name isEqual:@"QAIntel"]) expected=@"Loaded";
#endif
  if([name isEqual:@"QAInvalidSignature"]) expected=@"Blocked";
  NSCAssert([state isEqual:expected],@"%@: expected %@, got %@",name,expected,state);
  NSCAssert(protectedDepth==0,@"Crash protection must unwind even after exceptions");
  NSCAssert((plugins[name]!=nil)==[expected isEqual:@"Loaded"],@"Failed plugins must not enter menu registration");
 }
 NSCAssert(NSClassFromString(@"QAUniversal")!=Nil,@"Compatible code must load after leaving protected mode");
 puts("PASS: protected-mode blocking and recovery, real universal/Intel/missing-class/initialization-failure/invalid-signature bundles and crash-protection cleanup");
} }
'''.replace('SIGNATURE_METHOD', signature_method).replace('METHOD', method)
with tempfile.TemporaryDirectory(prefix='horos-bundle-load-') as directory:
    p=Path(directory)
    subprocess.run(['python3',str(root/'tools/generate-plugin-load-fixtures.py'),str(p/'fixtures')],check=True)
    (p/'test.m').write_text(program)
    subprocess.run(['xcrun','clang','-framework','Foundation','-framework','Security','-I',str(root/'Horos/Sources'),str(p/'test.m'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test'),str(p/'fixtures')],check=True,timeout=30)
