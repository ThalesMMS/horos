#!/usr/bin/env python3
"""The OS version predicates must keep saying yes as macOS version numbers grow."""
from pathlib import Path
import subprocess, sys, tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/AppController.m'
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path])
          if len(sys.argv) > 1 else (root / path).read_bytes()).decode('latin1')

start = source.index('+(BOOL) hasMacOSX1083')
end = source.index('+ (void) createNoIndexDirectoryIfNecessary:')
predicates = source[start:end]

code = r'''
#import <Foundation/Foundation.h>

static NSOperatingSystemVersion current;

@interface AppController : NSObject
+ (NSOperatingSystemVersion)operatingSystemVersion;
+ (BOOL) hasMacOSX1083;
+ (BOOL) hasMacOSXSierra;
+ (BOOL) hasMacOSXElCapitan;
+ (BOOL) hasMacOSXYosemite;
+ (BOOL) hasMacOSXMaverick;
+ (BOOL) hasMacOSXMountainLion;
+ (BOOL) hasMacOSXLion;
+ (BOOL) hasMacOSXSnowLeopard;
+ (BOOL) hasMacOSXLeopard;
@end

@implementation AppController
+ (NSOperatingSystemVersion)operatingSystemVersion { return current; }
PREDICATES
@end

#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s (at %ld.%ld.%ld)",#__VA_ARGS__,\
  (long)current.majorVersion,(long)current.minorVersion,(long)current.patchVersion);return 1;}}while(0)

static void at(NSInteger major, NSInteger minor, NSInteger patch) {
    current = (NSOperatingSystemVersion){major, minor, patch};
}

int main(){@autoreleasepool{
 // Below every gate.
 at(10,6,8);
 check([AppController hasMacOSXLeopard] && [AppController hasMacOSXSnowLeopard]);
 check(![AppController hasMacOSXLion] && ![AppController hasMacOSXElCapitan]);

 at(10,10,5);
 check([AppController hasMacOSXYosemite]);
 check(![AppController hasMacOSXElCapitan] && ![AppController hasMacOSXSierra]);

 at(10,11,6);
 check([AppController hasMacOSXElCapitan] && [AppController hasMacOSXYosemite]);
 check(![AppController hasMacOSXSierra]);

 at(10,12,0);
 check([AppController hasMacOSXSierra] && [AppController hasMacOSXElCapitan]);

 // Every release from Big Sur on must satisfy every gate, however small the
 // minor number is: this is the comparison that used to lock the app out.
 NSArray *modern = @[@[@11,@0],@[@11,@7],@[@12,@6],@[@13,@0],@[@14,@4],
                     @[@15,@0],@[@26,@0],@[@26,@6],@[@27,@0],@[@100,@0]];
 for (NSArray *v in modern) {
   at([v[0] integerValue], [v[1] integerValue], 0);
   check([AppController hasMacOSXLeopard]);
   check([AppController hasMacOSXSnowLeopard]);
   check([AppController hasMacOSXLion]);
   check([AppController hasMacOSXMountainLion]);
   check([AppController hasMacOSXMaverick]);
   check([AppController hasMacOSXYosemite]);
   check([AppController hasMacOSXElCapitan]);
   check([AppController hasMacOSXSierra]);
   // The exact-version probe stays exact.
   check(![AppController hasMacOSX1083]);
 }

 // The exact probe matches only its own version.
 at(10,8,3); check([AppController hasMacOSX1083]);
 at(10,8,4); check(![AppController hasMacOSX1083]);
 at(10,8,0); check(![AppController hasMacOSX1083]);

 NSLog(@"PASS: 10.6 through 10.12 gate as expected, and 11, 12, 13, 14, 15, 26, 27 and beyond satisfy every gate whatever the minor version");
}}
'''.replace('PREDICATES', predicates)

with tempfile.TemporaryDirectory(prefix='horos-os-version-') as folder:
    p = Path(folder)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fsanitize=undefined',
                    '-fno-sanitize-recover=all', '-framework', 'Foundation',
                    str(p / 'test.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
