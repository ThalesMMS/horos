#!/usr/bin/env python3
"""Run production request initialization and iteration with injected DB outcomes.

The native --same-association probe covers the full C-GET path. This smaller
harness checks reset-before-failure and empty-result behavior without a database.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
path = 'Horos/Sources/OsiriXSCPDataHandler.mm'
source = (subprocess.check_output(['git', 'show', sys.argv[1] + ':' + path]).decode('latin1')
          if len(sys.argv) > 1 else (root / path).read_text(encoding='latin1'))
start = source.index('- (OFCondition)prepareMoveForDataSet:')
opening = source.index('{', start)
end = source.index('        NSPredicate *compressedSOPInstancePredicate', opening)
initialization = source[opening:end]
start = source.index('- (OFCondition)nextMoveObject:')
opening = source.index('{', start)
depth = 1
end = opening + 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
iterator = source[start:end]
code = r'''
#import <Foundation/Foundation.h>
#include <cassert>
#include <cstring>
using OFCondition = int;
static const OFCondition EC_Normal=0, EC_IllegalParameter=1;
@interface LogManager : NSObject
+ (id)currentLogManager;
- (void)addLogLine:(id)line;
@end
@implementation LogManager
+ (id)currentLogManager { return nil; }
- (void)addLogLine:(id)line {}
@end
@interface Harness : NSObject {
 NSArray *moveArray;
 int moveArrayEnumerator;
 NSMutableDictionary *logDictionary;
}
- (OFCondition)prepare:(NSArray*)newFiles fail:(BOOL)fail;
- (OFCondition)nextMoveObject:(char*)path;
@end
@implementation Harness
- (void)dealloc { [moveArray release]; [super dealloc]; }
- (OFCondition)prepare:(NSArray*)newFiles fail:(BOOL)fail
INITIALIZATION
        if(fail) @throw [NSException exceptionWithName:@"InjectedDatabaseFailure" reason:nil userInfo:nil];
        [moveArray release]; moveArray=[newFiles copy]; cond=EC_Normal;
    } @catch(NSException* error) {}
    [pool release]; return cond;
}
ITERATOR
@end
int main(){ @autoreleasepool {
 Harness *h=[Harness new];char path[1024]={};
 assert(([h prepare:@[@"first",@"second",@"third"] fail:NO]==EC_Normal));
 assert([h nextMoveObject:path]==EC_Normal && !strcmp(path,"first"));
 assert([h nextMoveObject:path]==EC_Normal && !strcmp(path,"second"));
 assert(([h prepare:@[@"new-first",@"new-second"] fail:NO]==EC_Normal));
 assert([h nextMoveObject:path]==EC_Normal && !strcmp(path,"new-first"));
 assert(([h prepare:nil fail:YES]==EC_IllegalParameter));
 assert([h nextMoveObject:path]==EC_IllegalParameter); // no stale new-second
 assert(([h prepare:@[] fail:NO]==EC_Normal));
 assert([h nextMoveObject:path]==EC_IllegalParameter);
 assert(([h prepare:@[@"last"] fail:NO]==EC_Normal));
 assert([h nextMoveObject:path]==EC_Normal && !strcmp(path,"last"));
 assert([h nextMoveObject:path]==EC_IllegalParameter);
 [h release];
 puts("PASS: production initialization and iterator isolate successive, failed and empty retrieval requests");
} }
'''.replace('INITIALIZATION', initialization).replace('ITERATOR', iterator)
with tempfile.TemporaryDirectory(prefix='horos-retrieve-state-') as folder:
    p = Path(folder)
    (p / 'test.mm').write_text(code)
    subprocess.run(['clang++', '-std=c++11', '-framework', 'Foundation', str(p / 'test.mm'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True)
