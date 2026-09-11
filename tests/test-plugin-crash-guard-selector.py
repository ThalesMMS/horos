#!/usr/bin/env python3
"""Check that the "unknown plugin" diagnostic does not raise, and cannot skip launch.

`+[PluginManager startProtectForCrashWithFilter:]` matches a filter against the
loaded plugin bundles by `-class`, and its diagnostic for the no-match case
asked the filter for `-principalClass`, which belongs to NSBundle. Every filter
without a matching bundle therefore raised NSInvalidArgumentException out of
`-[AppController applicationWillFinishLaunching:]`, whose remaining statements
are DCMTK, the store SCP, the database and browser classes, the Web Portal, the
Bonjour publisher and the XML-RPC interface. The application stayed on screen
with none of them initialised.

The first check compiles the shipped body of the method and calls it with a
filter that matches nothing. The second requires the launch-time call into the
plugins to be inside a handler, so a third-party plugin cannot take the rest of
the sequence with it.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]


def source(name):
    path = 'Horos/Sources/' + name
    return (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
            if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')


plugins = source('PluginManager.m')
start = plugins.index('+ (void) startProtectForCrashWithFilter: (id) filter')
body = plugins[plugins.index('{', start) + 1:plugins.index('\n}\n', start)]

code = r'''
#import <Foundation/Foundation.h>
#include <stdio.h>
static NSMutableDictionary *pluginsBundleDictionnary = nil;
@interface PluginManager:NSObject
+ (void) startProtectForCrashWithPath:(NSString*)path;
+ (void) startProtectForCrashWithFilter: (id) filter;
@end
@implementation PluginManager
+ (void) startProtectForCrashWithPath:(NSString*)path { (void)path; }
+ (void) startProtectForCrashWithFilter: (id) filter
BODY
@end
// A filter is a plugin's filter instance, not its bundle: it answers -class and
// nothing else the diagnostic might reach for.
@interface ROIEnhancementFilter:NSObject
@end
@implementation ROIEnhancementFilter
@end
int main() {@autoreleasepool{
 // No bundle matches, which is the path that used to raise.
 pluginsBundleDictionnary = [NSMutableDictionary dictionary];
 @try {
  [PluginManager startProtectForCrashWithFilter: [[ROIEnhancementFilter alloc] init]];
 }
 @catch (NSException *e) {
  fprintf( stderr, "FAIL: the diagnostic raised %s: %s\n",
           [[e name] UTF8String], [[e reason] UTF8String]);
  return 1;
 }
 // A real bundle in the dictionary must still be matched by principal class.
 pluginsBundleDictionnary = [NSMutableDictionary dictionaryWithObject: [NSBundle mainBundle] forKey: @"main"];
 @try {
  [PluginManager startProtectForCrashWithFilter: [[ROIEnhancementFilter alloc] init]];
 }
 @catch (NSException *e) {
  fprintf( stderr, "FAIL: the diagnostic raised %s with a bundle present: %s\n",
           [[e name] UTF8String], [[e reason] UTF8String]);
  return 1;
 }
 puts("PASS: the unknown-plugin diagnostic returns instead of raising");
}}
'''.replace('BODY', '{' + body + '}')

with tempfile.TemporaryDirectory(prefix='horos-plugin-crash-guard-') as name:
    directory = Path(name)
    (directory / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-Wno-deprecated-declarations',
                    '-framework', 'Foundation', str(directory / 'test.m'),
                    '-o', str(directory / 'test')], check=True)
    subprocess.run([str(directory / 'test')], check=True)

# The launch sequence must survive a plugin that raises anyway.
controller = source('AppController.m')
launch = controller.index('- (void) applicationWillFinishLaunching:')
end = controller.index('\n}\n', launch)
method = controller[launch:end]
call = method.index('[PluginManager setMenus:')
before = method[:call]
# The call has to sit inside a @try whose @catch comes after it, and the
# statements that follow have to be outside that handler.
opened = before.rindex('@try') if '@try' in before else -1
if opened < 0:
    print('FAIL: the launch-time PluginManager call is not inside a @try', file=sys.stderr)
    raise SystemExit(1)
between = method[opened:call]
if '@catch' in between:
    print('FAIL: the nearest @try before the launch-time PluginManager call is already closed',
          file=sys.stderr)
    raise SystemExit(1)
after = method[call:]
if '@catch' not in after or not re.search(r'@catch[^{]*\{[^}]*\}', after, re.S):
    print('FAIL: the launch-time PluginManager call has no handler after it', file=sys.stderr)
    raise SystemExit(1)
for required in ('initDCMTK', 'restartSTORESCP', 'httpXMLRPCServer'):
    if required not in after[after.index('@catch'):]:
        print('FAIL: %s no longer follows the handler; the check has drifted' % required,
              file=sys.stderr)
        raise SystemExit(1)
print('PASS: the launch-time plugin menu setup is handled and the DICOM stack follows it')
