#!/usr/bin/env python3
"""Volume discovery must not hang, deadlock, or act on a volume that already went away."""
from pathlib import Path
import subprocess, tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
#import <Foundation/Foundation.h>
#import "HorosBoundedTask.h"
#import "HorosVolumeDiscovery.h"
#include <sys/types.h>
#include <signal.h>

#define check(...) do{if(!(__VA_ARGS__)){NSLog(@"FAIL: %s",#__VA_ARGS__);return 1;}}while(0)

static NSData *run(NSString *script, NSTimeInterval timeout, NSError **error) {
    return HorosRunBoundedTask(@"/bin/sh", @[@"-c", script], timeout, error);
}

int main(int argc, char **argv){@autoreleasepool{
 NSString *scratch = [NSString stringWithUTF8String:argv[1]];
 NSError *error = nil;

 // Ordinary reply.
 NSData *out = run(@"printf 'ok'", 5.0, &error);
 check(out && error == nil);
 check([[[NSString alloc] initWithData:out encoding:NSUTF8StringEncoding] autorelease].length == 2);

 // Far more than a pipe can hold. Draining only after exit would deadlock here,
 // which is how a wedged volume used to stall discovery.
 error = nil;
 out = run(@"i=0; while [ $i -lt 8192 ]; do printf '0123456789012345678901234567890123456789012345678901234567890123'; i=$((i+1)); done", 20.0, &error);
 check(error == nil);
 check(out.length == 8192*64);

 // A process that never answers is abandoned on the deadline, not waited on.
 error = nil;
 NSTimeInterval before = NSProcessInfo.processInfo.systemUptime;
 NSString *pidFile = [scratch stringByAppendingPathComponent:@"slow.pid"];
 out = run([NSString stringWithFormat:@"echo $$ > %@; sleep 60", pidFile], 0.5, &error);
 NSTimeInterval elapsed = NSProcessInfo.processInfo.systemUptime - before;
 check(out == nil && error != nil);
 check(elapsed < 5.0);

 // ...and it is actually gone afterwards, not left running against the volume.
 NSString *recorded = [NSString stringWithContentsOfFile:pidFile encoding:NSUTF8StringEncoding error:NULL];
 check(recorded.intValue > 0);
 BOOL reaped = NO;
 for (int i = 0; i < 100 && !reaped; i++) {
     if (kill(recorded.intValue, 0) != 0) reaped = YES;
     else [NSThread sleepForTimeInterval:0.02];
 }
 check(reaped);

 // A partial answer is a recoverable failure, never a partial plist.
 error = nil;
 out = run(@"printf 'half'; exit 3", 5.0, &error);
 check(out == nil && error != nil);

 // Runaway output is capped rather than accumulated without bound.
 error = nil;
 out = run(@"i=0; while [ $i -lt 40000 ]; do printf '01234567890123456789012345678901234567890123456789012345678901234567890123456789'; i=$((i+1)); done", 30.0, &error);
 check(out == nil && error != nil);

 // A missing tool reports rather than raises.
 error = nil;
 out = HorosRunBoundedTask(@"/usr/sbin/there-is-no-such-tool", @[], 5.0, &error);
 check(out == nil && error != nil);

 // Repeated use must not trip over its own file handles.
 for (int i = 0; i < 25; i++) {
     error = nil;
     check(run(@"printf 'x'", 5.0, &error) != nil && error == nil);
 }

 // The caller may ignore the error out-parameter.
 check(run(@"exit 1", 5.0, NULL) == nil);

 // The discovery layer around it: the wait happens off the main thread, the
 // answer comes back on it, and a volume that goes away is not acted on.
 HorosVolumeDiscovery *discovery = [[HorosVolumeDiscovery alloc] init];
 __block BOOL workerOffMain = NO, completedOnMain = NO;
 __block int completions = 0;
 check([discovery discoverPath:@"/Volumes/probe" worker:^id{
     workerOffMain = !NSThread.isMainThread;
     [NSThread sleepForTimeInterval:0.05];
     return @1;
 } completion:^(id value){ completions++; completedOnMain = NSThread.isMainThread; }]);
 // A second request for the same volume while the first is in flight is refused.
 check([discovery discoverPath:@"/Volumes/probe" worker:^id{ return @2; } completion:^(id v){ completions++; }] == NO);
 [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:1.0]];
 check(workerOffMain && completedOnMain && completions == 1);

 // Unmounted mid-flight: the completion is dropped rather than adding a source
 // for a volume that is no longer there.
 __block int stale = 0;
 check([discovery discoverPath:@"/Volumes/gone" worker:^id{
     [NSThread sleepForTimeInterval:0.2]; return @1;
 } completion:^(id v){ stale++; }]);
 [discovery cancelPath:@"/Volumes/gone"];
 [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:1.0]];
 check(stale == 0);
 // Remounting afterwards is accepted again.
 check([discovery discoverPath:@"/Volumes/gone" worker:^id{ return @1; } completion:^(id v){ stale++; }]);
 [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:1.0]];
 check(stale == 1);

 // A worker that raises does not take the discovery down with it.
 __block id raised = @1;
 check([discovery discoverPath:@"/Volumes/raise" worker:^id{
     [NSException raise:@"probe" format:@"worker failed"]; return @1;
 } completion:^(id v){ raised = v; }]);
 [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:1.0]];
 check(raised == nil);
 [discovery cancelAll];
 [discovery release];

 NSLog(@"PASS: output beyond the pipe capacity, enforced deadline with the child reaped, capped output, failing and missing tools, repeated use; discovery waits off the main thread and drops results for volumes that went away");
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-bounded-task-') as folder:
    p = Path(folder)
    (p / 'test.m').write_text(code)
    subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-framework', 'Foundation',
                    '-I', str(root / 'Horos/Sources'), str(p / 'test.m'), '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test'), str(p)], check=True)
