#!/usr/bin/env python3
"""-setMenus goes only to the filters that implement it (#650).

`+[PluginManager setMenus::::]` ends by sending `-setMenus` to every registered
filter. The method is `PluginFilter`'s, and the app's own Swift filters, ROI
Enhancement and T2 Fit Map, are plain NSObjects: at every launch the loop raised
two NSInvalidArgumentExceptions, caught and logged ("***** exception in
+[PluginManager setMenus::::]: -[ROIEnhancementFilter setMenus]: unrecognized
selector").

The shipped loop is compiled here over a filter that implements `-setMenus`, one
that does not, and a plugin whose `-setMenus` raises: the first is called once,
the second is passed over without an exception, and the third's exception is
still caught, each inside the crash guard.

    python3 tests/test-plugin-set-menus.py [<git revision>]
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/PluginManager.m'
source = (subprocess.check_output(['git', '-C', str(root), 'show', sys.argv[1] + ':' + path])
          if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')

method = source.index('+ (void) setMenus:(NSMenu*) filtersMenu :(NSMenu*) roisMenu :(NSMenu*) othersMenu :(NSMenu*) dbMenu')
start = source.index('\tNSEnumerator *pluginEnum = [plugins objectEnumerator];', method)
loop = source.index('while( pluginFilter = [pluginEnum nextObject])', start)
opening = source.index('{', loop)
depth = 0
for end in range(opening, len(source)):
    if source[end] == '{':
        depth += 1
    elif source[end] == '}':
        depth -= 1
        if depth == 0:
            break
body = source[start:end + 1]

code = r'''
#import <Foundation/Foundation.h>
#include <stdio.h>
// The loop logs what it catches: counted here.
static int guards = 0, openGuards = 0, logged = 0;
#define NSLog(format, ...) (logged++, (void)fprintf(stderr, "%s\n", [[NSString stringWithFormat:format, ##__VA_ARGS__] UTF8String]))
static NSMutableDictionary *plugins = nil;
@interface PluginFilter : NSObject
- (void)setMenus;
@end
@implementation PluginFilter
- (void)setMenus {}
@end
// A plugin that makes its menu changes.
@interface MenuPlugin : PluginFilter
@property int calls;
@end
@implementation MenuPlugin
- (void)setMenus { self.calls++; }
@end
// A plugin whose menu changes fail: still caught, never stops the loop.
@interface FailingPlugin : PluginFilter
@end
@implementation FailingPlugin
- (void)setMenus { [NSException raise:@"PluginFailure" format:@"a plugin's own failure"]; }
@end
// What ROIEnhancementFilter and T2FitMapFilter are: registered filters that are not PluginFilters.
@interface NativeFilter : NSObject
@end
@implementation NativeFilter
@end
@interface PluginManager : NSObject
+ (void)startProtectForCrashWithFilter:(id)filter;
+ (void)endProtectForCrash;
+ (void)runLoop;
@end
@implementation PluginManager
+ (void)startProtectForCrashWithFilter:(id)filter { guards++; openGuards++; }
+ (void)endProtectForCrash { openGuards--; }
+ (void)runLoop
{
BODY
}
@end
int main(void) {
    @autoreleasepool {
        MenuPlugin *menu = [MenuPlugin new];
        plugins = [@{@"Menu plugin": menu, @"ROI Enhancement": [NativeFilter new], @"T2 Fit Map": [NativeFilter new],
                     @"Failing plugin": [FailingPlugin new]} mutableCopy];
        [PluginManager runLoop];
        int failed = 0;
        if (menu.calls != 1) { printf("FAIL: the plugin that implements -setMenus was called %d times\n", menu.calls); failed++; }
        if (logged != 1) { printf("FAIL: %d exceptions logged, only the failing plugin's expected\n", logged); failed++; }
        if (guards != 4 || openGuards != 0) { printf("FAIL: %d crash guards opened, %d left open\n", guards, openGuards); failed++; }
        if (failed) return 1;
        puts("ok");
    }
    return 0;
}
'''.replace('BODY', body)

with tempfile.TemporaryDirectory(prefix='horos-set-menus-') as temporary:
    work = Path(temporary)
    (work / 'main.m').write_text(code)
    built = subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-Wno-objc-method-access', '-framework', 'Foundation',
                            str(work / 'main.m'), '-o', str(work / 'probe')], capture_output=True, text=True)
    if built.returncode != 0:
        print('FAIL: the loop does not build: ' + built.stderr[-2000:])
        raise SystemExit(1)
    run = subprocess.run([str(work / 'probe')], capture_output=True, text=True, timeout=30)
    if run.returncode != 0:
        print((run.stdout + run.stderr).strip())
        raise SystemExit(1)
print('-setMenus: sent to the plugin that implements it, not to the native filters; a plugin failure still caught')
