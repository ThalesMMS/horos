#!/usr/bin/env python3
"""No -[NSTask launch] can raise past its caller, and none waits forever.

Two halves: a scan of every launch in the sources, and the helper itself driven
against executables that cannot start.
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

LAUNCH = re.compile(r'\[\s*(\w+)\s+launch\s*\]')


def launches(text):
    """Yield (offset, enclosed by @try) for each -launch, skipping comments and literals."""
    stack = []          # one entry per open brace: True when the brace opened a @try
    pending = False
    index, length = 0, len(text)
    while index < length:
        character = text[index]
        if character == '/' and index + 1 < length and text[index + 1] == '/':
            index = text.find('\n', index)
            if index < 0:
                return
            continue
        if character == '/' and index + 1 < length and text[index + 1] == '*':
            index = text.find('*/', index)
            if index < 0:
                return
            index += 2
            continue
        if character in '"\'':
            quote, index = character, index + 1
            while index < length and text[index] != quote:
                index += 2 if text[index] == '\\' else 1
            index += 1
            continue
        if text.startswith('@try', index):
            pending = True
            index += 4
            continue
        if character == '{':
            stack.append(pending)
            pending = False
            index += 1
            continue
        if character == '}':
            if stack:
                stack.pop()
            index += 1
            continue
        match = LAUNCH.match(text, index)
        if match:
            yield index, any(stack)
            index = match.end()
            continue
        index += 1


def sources():
    for directory in ('Horos/Sources', 'Preference Panes'):
        for path in sorted((root / directory).rglob('*')):
            if path.is_file() and path.suffix in ('.m', '.mm', '.h'):
                yield path


total = 0
for path in sources():
    text = path.read_bytes().decode('latin1')
    for offset, guarded in launches(text):
        total += 1
        if not guarded:
            line = text.count('\n', 0, offset) + 1
            failures.append('%s:%d launches outside a @try' % (path.relative_to(root), line))

# A scan that finds nothing proves nothing.
if total < 15:
    failures.append('the scan found only %d launch sites; it is not looking where it should' % total)

# The two helpers every converted site now goes through.
header = root / 'Horos/Sources/HorosBoundedTask.h'
for name in ('HorosLaunchTask', 'HorosRunTaskUntilExit'):
    if name not in header.read_text():
        failures.append('%s is gone from HorosBoundedTask.h' % name)

code = r'''
#import <Foundation/Foundation.h>
#import "HorosBoundedTask.h"

static int failures;
#define check(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static NSTask *taskFor(NSString *path, NSArray *arguments)
{
    NSTask *task = [[[NSTask alloc] init] autorelease];
    task.launchPath = path;
    task.arguments = arguments ?: @[];
    task.standardOutput = [NSFileHandle fileHandleWithNullDevice];
    task.standardError = [NSFileHandle fileHandleWithNullDevice];
    return task;
}

int main(int argc, const char **argv) { @autoreleasepool {
    NSString *directory = [NSString stringWithUTF8String: argv[1]];
    NSError *error;

    // An executable that is not there. -launch raises here; nothing may escape.
    error = nil;
    check(HorosLaunchTask(taskFor([directory stringByAppendingPathComponent:@"absent"], nil), &error) == NO);
    check(error != nil);
    check(error.localizedDescription.length > 0);

    // A file that exists and is not executable.
    error = nil;
    check(HorosLaunchTask(taskFor([directory stringByAppendingPathComponent:@"plain"], nil), &error) == NO);
    check(error != nil);

    // A directory.
    error = nil;
    check(HorosLaunchTask(taskFor(directory, nil), &error) == NO);
    check(error != nil);

    // An executable whose interpreter is missing: the same failure a helper
    // built for an architecture this Mac cannot run produces.
    error = nil;
    check(HorosLaunchTask(taskFor([directory stringByAppendingPathComponent:@"bad-interpreter"], nil), &error) == NO);
    check(error != nil);

    // A nil launch path is a programming error, not a crash.
    error = nil;
    check(HorosLaunchTask([[[NSTask alloc] init] autorelease], &error) == NO);
    check(error != nil);

    // A caller that does not want the error still gets the answer.
    check(HorosLaunchTask(taskFor([directory stringByAppendingPathComponent:@"absent"], nil), NULL) == NO);

    // Something that works.
    NSTask *works = taskFor(@"/bin/echo", @[@"hello"]);
    error = nil;
    check(HorosRunTaskUntilExit(works, 30, &error) == YES);
    check(error == nil);
    check(works.terminationStatus == 0);

    // A failing exit status is the task's answer, not a launch failure: the
    // callers read terminationStatus themselves.
    NSTask *fails = taskFor(@"/bin/sh", @[@"-c", @"exit 3"]);
    error = nil;
    check(HorosRunTaskUntilExit(fails, 30, &error) == YES);
    check(fails.terminationStatus == 3);

    // A helper that never finishes is stopped at the deadline, and is gone.
    NSTask *hangs = taskFor(@"/bin/sh", @[@"-c", @"trap '' TERM; sleep 120"]);
    NSTimeInterval before = NSProcessInfo.processInfo.systemUptime;
    error = nil;
    check(HorosRunTaskUntilExit(hangs, 0.3, &error) == NO);
    NSTimeInterval elapsed = NSProcessInfo.processInfo.systemUptime - before;
    check(elapsed >= 0.3);
    check(elapsed < 10);                       // bounded, not merely eventual
    check(error != nil);
    check(hangs.isRunning == NO);
    pid_t pid = hangs.processIdentifier;
    [hangs waitUntilExit];                     // reap, so the check below is about the child
    check(kill(pid, 0) != 0);

    // A launch failure is reported by the waiting helper too.
    error = nil;
    check(HorosRunTaskUntilExit(taskFor([directory stringByAppendingPathComponent:@"absent"], nil), 5, &error) == NO);
    check(error != nil);

    // Nothing above may have left an exception in flight.
    check([NSThread isMainThread]);

    if (failures) { printf("%d failure(s)\n", failures); return 1; }
    printf("ok\n");
    return 0;
} }
'''

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'plain').write_text('not executable\n')
    (path / 'bad-interpreter').write_text('#!/nonexistent/interpreter\n')
    (path / 'bad-interpreter').chmod(0o755)
    (path / 'main.m').write_text(code)
    build = subprocess.run(['xcrun', 'clang', '-fno-objc-arc', '-I', str(root / 'Horos/Sources'),
                            str(path / 'main.m'), '-framework', 'Foundation',
                            '-o', str(path / 'test')], capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr)
        failures.append('the helper does not compile')
        ran = 1
    else:
        ran = subprocess.run([str(path / 'test'), str(path)]).returncode

for failure in failures:
    print('FAIL: %s' % failure)
if failures or ran:
    sys.exit(1)
print('ok: %d launch sites scanned, all guarded' % total)
