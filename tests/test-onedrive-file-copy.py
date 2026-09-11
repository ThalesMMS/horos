#!/usr/bin/env python3
"""Publication copy must refuse unhydrated OneDrive sources and keep originals."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
helper = root / 'Horos/Sources/CloudFileAccess.swift'
header = root / 'Horos/Sources/HorosFileCopy.h'
if not helper.exists() or not header.exists():
    print('FAIL: cloud copy helpers are missing')
    sys.exit(1)

program = r'''
#import "HorosFileCopy.h"
@interface HorosCloudFileAccess : NSObject
+ (BOOL)setFixturePresence:(NSString *)value atPath:(NSString *)path error:(NSError **)error;
@end
int main(int argc, char **argv) {
 @autoreleasepool {
  NSString *root = [NSString stringWithUTF8String:argv[1]];
  NSFileManager *manager = NSFileManager.defaultManager;
  NSString *oneDrive = [root stringByAppendingPathComponent:@"Library/CloudStorage/OneDrive-Personal"];
  NSError *createError = nil;
  if (![manager createDirectoryAtPath:oneDrive withIntermediateDirectories:YES attributes:nil error:&createError])
   return 1;
  NSString *hydrated = [oneDrive stringByAppendingPathComponent:@"hydrated.dcm"];
  NSString *placeholder = [oneDrive stringByAppendingPathComponent:@"placeholder.dcm"];
  NSString *offline = [oneDrive stringByAppendingPathComponent:@"offline.dcm"];
  NSString *local = [root stringByAppendingPathComponent:@"local.dcm"];
  [@"hydrated-bytes" writeToFile:hydrated atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  [@"placeholder-bytes" writeToFile:placeholder atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  [@"offline-bytes" writeToFile:offline atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  [@"local-bytes" writeToFile:local atomically:YES encoding:NSUTF8StringEncoding error:NULL];
  Class cloud = NSClassFromString(@"HorosCloudFileAccess");
  NSCAssert(cloud, @"HorosCloudFileAccess must be linked");
  NSError *attrError = nil;
  if (![cloud setFixturePresence:@"placeholder" atPath:placeholder error:&attrError]) return 2;
  if (![cloud setFixturePresence:@"offline" atPath:offline error:&attrError]) return 3;

  NSError *error = nil;
  NSString *outHydrated = [root stringByAppendingPathComponent:@"out-hydrated.dcm"];
  NSCAssert(HorosCopyFileForPublication(manager, hydrated, outHydrated, NO, &error), @"hydrated copy: %@", error);
  NSCAssert([[NSData dataWithContentsOfFile:outHydrated] isEqual:[@"hydrated-bytes" dataUsingEncoding:NSUTF8StringEncoding]], @"hydrated bytes");

  NSString *outLocal = [root stringByAppendingPathComponent:@"out-local.dcm"];
  NSCAssert(HorosCopyFileForPublication(manager, local, outLocal, NO, &error), @"local copy: %@", error);

  NSString *outPlaceholder = [root stringByAppendingPathComponent:@"out-placeholder.dcm"];
  NSCAssert(!HorosCopyFileForPublication(manager, placeholder, outPlaceholder, NO, &error), @"placeholder must fail");
  NSCAssert(error, @"placeholder must report an error");
  NSCAssert([error.localizedDescription containsString:@"hydrated"] || [error.localizedDescription containsString:@"available offline"], @"hydration text: %@", error);
  NSCAssert(![error.localizedDescription containsString:@".horos-copy-"], @"do not expose staging");
  NSCAssert(![manager fileExistsAtPath:outPlaceholder], @"placeholder must not publish");
  NSCAssert([[NSString stringWithContentsOfFile:placeholder encoding:NSUTF8StringEncoding error:NULL] isEqual:@"placeholder-bytes"], @"preserve placeholder source");

  NSString *outOffline = [root stringByAppendingPathComponent:@"out-offline.dcm"];
  NSCAssert(!HorosCopyFileForPublication(manager, offline, outOffline, NO, &error), @"offline must fail");
  NSCAssert(![manager fileExistsAtPath:outOffline], @"offline must not publish");
  NSCAssert([[NSString stringWithContentsOfFile:offline encoding:NSUTF8StringEncoding error:NULL] isEqual:@"offline-bytes"], @"preserve offline source");

  NSArray *owned = [[manager contentsOfDirectoryAtPath:root error:NULL] filteredArrayUsingPredicate:
   [NSPredicate predicateWithFormat:@"SELF BEGINSWITH %@", @".horos-copy-"]];
  NSCAssert(owned.count == 0, @"staging residue: %@", owned);
  puts("PASS: coordinated copy publishes hydrated/local files and refuses placeholder/offline without residue");
 }
 return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='horos-onedrive-copy-') as directory:
    folder = Path(directory)
    (folder / 'test.m').write_text(program)
    library = folder / 'libCloudFileAccess.dylib'
    built_swift = subprocess.run(
        ['xcrun', '--sdk', 'macosx', 'swiftc', '-emit-library', '-o', str(library),
         '-module-name', 'Horos', str(helper)],
        capture_output=True, text=True)
    if built_swift.returncode != 0:
        print('FAIL: CloudFileAccess library did not compile:\n%s' % built_swift.stderr[-2000:])
        sys.exit(1)
    binary = folder / 'test'
    built = subprocess.run(
        ['xcrun', 'clang', '-fsanitize=address', '-framework', 'Foundation', '-framework', 'AppKit',
         '-I', str(root / 'Horos/Sources'), str(folder / 'test.m'), str(library),
         '-Wl,-rpath,' + str(folder), '-o', str(binary)],
        capture_output=True, text=True)
    if built.returncode != 0:
        print('FAIL: coordinated copy driver did not compile:\n%s' % built.stderr[-2000:])
        sys.exit(1)
    data = folder / 'data'
    data.mkdir()
    run = subprocess.run([str(binary), str(data)], capture_output=True, text=True, timeout=30)
    if run.returncode != 0:
        print('FAIL: coordinated copy driver failed:\n%s%s' % (run.stderr[-1500:], run.stdout[-500:]))
        sys.exit(1)
    if 'PASS:' not in run.stdout:
        print('FAIL: no pass line:\n%s' % run.stdout)
        sys.exit(1)
print(run.stdout.strip())
