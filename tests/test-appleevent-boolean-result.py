#!/usr/bin/env python3
"""Exercise real AppleScript boolean replies through Nitrogen's converter."""
import argparse
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=root / 'Nitrogen/Sources/NSAppleEventDescriptor+N2.mm')
args = parser.parse_args()
program = r'''
#import <Cocoa/Cocoa.h>
#import "NSAppleEventDescriptor+N2.h"
int main() { @autoreleasepool {
    NSArray *sources = @[@"return true", @"return false", @"return {true, false, 2 > 1}"];
    NSArray *expected = @[@YES, @NO, (@[@YES, @NO, @YES])];
    for (NSUInteger i=0; i<sources.count; ++i) {
        NSAppleScript *script=[[[NSAppleScript alloc] initWithSource:sources[i]] autorelease];
        NSDictionary *error=nil;
        NSAppleEventDescriptor *result=[script executeAndReturnError:&error];
        if (error || !result) return 1;
        @try { if (![[result object] isEqual:expected[i]]) return 1; }
        @catch (NSException *exception) { fprintf(stderr,"%s\n",exception.reason.UTF8String); return 1; }
    }
    for (NSNumber *value in @[@YES, @NO]) {
        NSAppleEventDescriptor *descriptor=[NSAppleEventDescriptor descriptorWithBoolean:value.boolValue];
        if (![[descriptor object] isEqual:value]) return 1;
    }
    puts("PASS: real AppleScript true/false and nested boolean replies; ordinary boolean descriptors preserved");
} }
'''
with tempfile.TemporaryDirectory(prefix='horos-appleevent-bool-') as temp:
    directory = Path(temp)
    source = directory / 'main.mm'
    source.write_text(program)
    binary = directory / 'test'
    subprocess.run(['xcrun', 'clang++', '-fno-objc-arc', '-Wno-deprecated-declarations',
                    '-I', str(root / 'Nitrogen/Sources'), str(args.source), str(source),
                    '-framework', 'Cocoa', '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
