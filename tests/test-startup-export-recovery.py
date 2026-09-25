#!/usr/bin/env python3
"""Execute the production startup recovery block with real filesystem entries."""
import argparse
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=root / 'Horos/Sources/AppController.m')
args = parser.parse_args()
source = args.source.read_bytes().decode('latin1')
# The recovery block is the braced block between these two statements.
start = source.index('[self initTilingWindows];') + len('[self initTilingWindows];')
end = source.index('if( [AppController isKDUEngineAvailable])', start)
recovery = source[start:end]
program = r'''
#import <Foundation/Foundation.h>
#import "RecoveryTest-Swift.h"
static NSString *temporary, *decompression, *incoming;
@interface DicomDatabase : NSObject
+ (id)activeLocalDatabase;
- (NSString*)tempDirPath;
- (NSString*)decompressionDirPath;
- (NSString*)incomingDirPath;
@end
@implementation DicomDatabase
+ (id)activeLocalDatabase { return [[[self alloc] init] autorelease]; }
- (NSString*)tempDirPath { return temporary; }
- (NSString*)decompressionDirPath { return decompression; }
- (NSString*)incomingDirPath { return incoming; }
@end
@interface NSFileManager (TestEnumeration)
- (NSEnumerator*)enumeratorAtPath:(NSString*)path filesOnly:(BOOL)filesOnly recursive:(BOOL)recursive;
@end
@implementation NSFileManager (TestEnumeration)
- (NSEnumerator*)enumeratorAtPath:(NSString*)path filesOnly:(BOOL)filesOnly recursive:(BOOL)recursive {
    NSCAssert(!filesOnly && !recursive, @"production recovery enumerates direct children");
    return [[self contentsOfDirectoryAtPath:path error:NULL] objectEnumerator];
}
@end
static void recover(void) {
RECOVERY
}
static void writeFixture(NSString *root, NSString *name) {
    NSString *path=[root stringByAppendingPathComponent:name];
    [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent
                         withIntermediateDirectories:YES attributes:nil error:NULL];
    [@"preserved fixture bytes" writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:NULL];
}
static BOOL intact(NSString *root, NSString *name) {
    return [[NSString stringWithContentsOfFile:[root stringByAppendingPathComponent:name]
                                     encoding:NSUTF8StringEncoding error:NULL] isEqual:@"preserved fixture bytes"];
}
#define CHECK(value, message) if (!(value)) { fputs(message "\n", stderr); return 1; }
int main(int argc, char **argv) { @autoreleasepool {
    NSString *root=[NSString stringWithUTF8String:argv[1]];
    temporary=[root stringByAppendingPathComponent:@"TEMP.noindex"];
    decompression=[root stringByAppendingPathComponent:@"DECOMPRESSION.noindex"];
    incoming=[root stringByAppendingPathComponent:@"INCOMING.noindex"];
    NSArray *exports=@[@"EXPORT/0001.jpg", @"EXPORT-74E335A4-D689-4E8E-837F-F68C2D338536/0001.jpg"];
    NSArray *received=@[@"received.dcm", @"EXPORT-received-series/image.dcm", @"EXPORT-77A064F6-249D-40B0-87B4-38F0DD5819FA"];
    NSArray *compressed=@[@"decompressed.dcm", @"EXPORT-0779CBB5-F953-4A54-921F-655EE22F38C0/image.dcm"];
    for (NSString *name in exports) writeFixture(temporary,name);
    for (NSString *name in received) writeFixture(temporary,name);
    for (NSString *name in compressed) writeFixture(decompression,name);
    writeFixture(incoming,@"already.dcm");
    recover();
    for (NSString *name in exports) {
        CHECK(intact(temporary,name), "exported attachment was moved or changed by recovery");
        CHECK(!intact(incoming,name), "export was handed to the DICOM importer");
    }
    for (NSString *name in received) {
        CHECK(intact(incoming,name) && !intact(temporary,name), "received entry was not recovered");
    }
    for (NSString *name in compressed) {
        CHECK(intact(incoming,name) && !intact(decompression,name), "decompression entry was not recovered");
    }
    CHECK(intact(incoming,@"already.dcm"), "existing incoming data changed");
    recover();
    for (NSString *name in exports) CHECK(intact(temporary,name), "repeated recovery changed export");
    puts("PASS: current/legacy exports retained; received files, unrelated folders and decompression recovered; second pass preserves bytes");
} }
'''.replace('RECOVERY', recovery)

with tempfile.TemporaryDirectory(prefix='horos-startup-export-') as folder:
    path = Path(folder)
    (path / 'main.m').write_text(program)
    subprocess.run(['xcrun', 'swiftc', '-sanitize=address', '-emit-library', '-emit-objc-header',
                    '-module-name', 'RecoveryTest', '-emit-objc-header-path', str(path / 'RecoveryTest-Swift.h'),
                    str(root / 'Horos/Sources/ImageExportPath.swift'), '-o', str(path / 'libRecoveryTest.dylib')], check=True)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fblocks', '-fsanitize=address', '-framework', 'Foundation',
                    '-I', str(path), '-L', str(path), '-lRecoveryTest', '-Wl,-rpath,' + str(path),
                    str(path / 'main.m'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test'), str(path / 'files')], check=True)
