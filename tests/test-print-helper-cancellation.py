#!/usr/bin/env python3
"""#384 A cancellation reaps an in-flight report helper before spool cleanup."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
code = r'''
#import "HorosBoundedTask.h"
int main(void) { @autoreleasepool {
    NSTask *task = [[[NSTask alloc] init] autorelease];
    task.launchPath = @"/bin/sleep";
    task.arguments = @[@"60"];
    __block int checkpoints = 0;
    NSError *error = nil;
    NSTimeInterval start = NSProcessInfo.processInfo.systemUptime;
    BOOL success = HorosRunTaskUntilExitCheckingCancellation(task, 10, ^BOOL { return ++checkpoints == 3; }, &error);
    if (success || checkpoints != 3 || task.isRunning || error == nil ||
        ![error.localizedDescription containsString:@"cancelled"] ||
        NSProcessInfo.processInfo.systemUptime - start > 3) return 1;
    puts("PASS: report helper cancellation runs at a checkpoint, returns failure and reaps the child before cleanup");
    return 0;
}}
'''
with tempfile.TemporaryDirectory(prefix='horos-print-384-cancel-') as temporary:
    folder = Path(temporary)
    (folder/'Check.m').write_text(code)
    subprocess.run(['xcrun','clang','-fblocks','-I',str(root/'Horos/Sources'),'-framework','Foundation',str(folder/'Check.m'),'-o',str(folder/'check')],check=True,timeout=30)
    subprocess.run([str(folder/'check')],check=True,timeout=10)
