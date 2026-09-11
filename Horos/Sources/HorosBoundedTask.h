#import <Foundation/Foundation.h>
#include <fcntl.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>

// -[NSTask launch] raises NSInvalidArgumentException when the executable cannot
// start: absent, not executable, or built for an architecture this Mac cannot
// run. Nothing in this application wants that exception unwinding to the event
// loop, so every launch goes through here. launchAndReturnError: reports most of
// those as errors; the @catch covers the rest, including a launch path the
// caller never checked.
static inline BOOL HorosLaunchTask(NSTask *task, NSError **error)
{
    NSError *failure = nil;
    @try {
        if ([task launchAndReturnError: &failure])
            return YES;
    }
    @catch (NSException *exception) {
        failure = [NSError errorWithDomain:@"HorosTaskLaunch" code:2 userInfo:@{
            NSLocalizedDescriptionKey: exception.reason ?: @"The helper tool could not be started."}];
    }
    if (failure == nil)
        failure = [NSError errorWithDomain:@"HorosTaskLaunch" code:1 userInfo:@{
            NSLocalizedDescriptionKey: @"The helper tool could not be started."}];
    if (error) *error = failure;
    return NO;
}

// Starts a task and waits for it, for at most `timeout` seconds. The callers
// this replaces polled -isRunning with no deadline at all, several of them on
// the main thread, so a helper that never exited hung the application.
//
// Returns NO when the task could not start or outlived its deadline; the
// caller reads -terminationStatus for what the task itself reported. A task
// that runs out of time is asked to stop and then killed, so nothing is left
// behind.
static inline BOOL HorosRunTaskUntilExit(NSTask *task, NSTimeInterval timeout, NSError **error)
{
    if (!HorosLaunchTask(task, error))
        return NO;

    NSTimeInterval deadline = NSProcessInfo.processInfo.systemUptime + MAX(0.01, timeout);
    while (task.isRunning && NSProcessInfo.processInfo.systemUptime < deadline)
        [NSThread sleepForTimeInterval: 0.01];

    if (task.isRunning) {
        [task terminate];
        NSTimeInterval grace = NSProcessInfo.processInfo.systemUptime + 0.2;
        while (task.isRunning && NSProcessInfo.processInfo.systemUptime < grace)
            [NSThread sleepForTimeInterval: 0.01];
        if (task.isRunning) {
            kill(task.processIdentifier, SIGKILL);
            // SIGKILL cannot be refused, but -isRunning only turns NO once the
            // child has been reaped, so wait for that rather than handing the
            // caller a task that still claims to be running.
            NSTimeInterval reaped = NSProcessInfo.processInfo.systemUptime + 2;
            while (task.isRunning && NSProcessInfo.processInfo.systemUptime < reaped)
                [NSThread sleepForTimeInterval: 0.01];
        }
        if (error)
            *error = [NSError errorWithDomain:@"HorosTaskLaunch" code:3 userInfo:@{
                NSLocalizedDescriptionKey: @"The helper tool did not finish in time."}];
        return NO;
    }

    return YES;
}

typedef struct {
    NSTimeInterval timeout;
    // Some tools report on stderr; capture both streams for those.
    BOOL capturesStandardError;
    // A tool whose exit status reports findings rather than failure.
    BOOL allowsFailureStatus;
} HorosBoundedTaskOptions;

// Drain output while the process runs so pipe capacity cannot deadlock the caller.
static inline NSData *HorosRunBoundedTaskWithOptions(NSString *executable, NSArray *arguments,
                                                     HorosBoundedTaskOptions options, NSError **error)
{
    NSTimeInterval timeout = options.timeout;
    NSTask *task = [[[NSTask alloc] init] autorelease];
    NSPipe *pipe = [NSPipe pipe];
    NSMutableData *output = [NSMutableData data];
    NSString *failure = nil;
    BOOL launched = NO;
    @try {
        task.launchPath = executable;
        task.arguments = arguments;
        task.standardOutput = pipe;
        task.standardError = options.capturesStandardError ? (id)pipe : (id)[NSFileHandle fileHandleWithNullDevice];
        int fd = pipe.fileHandleForReading.fileDescriptor;
        int flags = fcntl(fd, F_GETFL);
        if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0)
            [NSException raise:@"BoundedTask" format:@"Could not configure process output."];
        [task launch]; launched = YES;
        [pipe.fileHandleForWriting closeFile];
        NSTimeInterval deadline = NSProcessInfo.processInfo.systemUptime + MAX(0.01,timeout);
        for (;;) {
            char bytes[16384];
            ssize_t count;
            while ((count = read(fd,bytes,sizeof(bytes))) > 0) {
                if (output.length + (NSUInteger)count > 2*1024*1024) { failure = @"Process output exceeded its limit."; break; }
                [output appendBytes:bytes length:(NSUInteger)count];
                if (NSProcessInfo.processInfo.systemUptime >= deadline) { failure = @"Process timed out."; break; }
            }
            if (failure) break;
            if (count < 0 && errno != EAGAIN && errno != EINTR) { failure = @"Could not read process output."; break; }
            if (!task.isRunning) break;
            if (NSProcessInfo.processInfo.systemUptime >= deadline) { failure = @"Process timed out."; break; }
            [NSThread sleepForTimeInterval:0.01];
        }
        // A final drain covers bytes written between the last read and exit.
        if (!failure) {
            char bytes[16384]; ssize_t count;
            while ((count = read(fd,bytes,sizeof(bytes))) > 0) {
                if (output.length + (NSUInteger)count > 2*1024*1024) { failure = @"Process output exceeded its limit."; break; }
                [output appendBytes:bytes length:(NSUInteger)count];
            }
            if (!options.allowsFailureStatus && task.terminationStatus != 0)
                failure = @"Process exited unsuccessfully.";
        }
    } @catch (NSException *exception) {
        failure = exception.reason ?: @"Process could not be launched.";
    } @finally {
        if (launched && task.isRunning) {
            [task terminate];
            NSTimeInterval deadline = NSProcessInfo.processInfo.systemUptime + 0.2;
            while (task.isRunning && NSProcessInfo.processInfo.systemUptime < deadline)
                [NSThread sleepForTimeInterval:0.01];
            if (task.isRunning) kill(task.processIdentifier,SIGKILL);
        }
        [pipe.fileHandleForReading closeFile];
        [pipe.fileHandleForWriting closeFile];
    }
    if (failure) {
        if (error) *error = [NSError errorWithDomain:@"HorosBoundedTask" code:1 userInfo:@{NSLocalizedDescriptionKey:failure}];
        return nil;
    }
    return output;
}

static inline NSData *HorosRunBoundedTask(NSString *executable, NSArray *arguments,
                                          NSTimeInterval timeout, NSError **error)
{
    HorosBoundedTaskOptions options = { .timeout = timeout };
    return HorosRunBoundedTaskWithOptions(executable, arguments, options, error);
}
