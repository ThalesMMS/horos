// Drives NSThread (N2) - +performBlockInBackground: and -setProgressDetails: -
// from linked objects (#626): the application's NSThread+N2.o, or the same source
// recompiled at another revision.
//
//   probe contract      one JSON object of observed behaviour
//   probe interleave <dylib A> <dylib B> <threads>
//       loads both revisions' objects as dylibs, keeps each one's
//       +performBlockInBackground: and -setProgressDetails:, alternates them
//       (ABBA; HOROS_AB_FIRST says which starts) and prints {"A": ..., "B": ...}
//
// Built without ARC, like the object it links.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <objc/runtime.h>
#include <stdatomic.h>

@interface NSThread (N2ThreadProbe)
+ (NSThread *)performBlockInBackground:(void (^)(void))block;
- (NSString *)status;
- (void)setStatus:(NSString *)status;
- (NSString *)progressDetails;
- (void)setProgressDetails:(NSString *)details;
- (void)setProgress:(CGFloat)progress;
- (void)setSupportsCancel:(BOOL)supportsCancel;
- (void)setSupportsBackgrounding:(BOOL)supportsBackgrounding;
- (void)setUniqueId:(NSString *)uniqueId;
- (void)setIsCancelled:(BOOL)isCancelled;
- (void)enterOperation;
- (void)exitOperation;
@end

static atomic_int deallocated = 0;
@interface Sentinel : NSObject @end
@implementation Sentinel
- (void)dealloc { atomic_fetch_add(&deallocated, 1); [super dealloc]; }
@end

@interface Counter : NSObject { @public atomic_int will, did, changes; }
@end
@implementation Counter
- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context {
    if ([change[NSKeyValueChangeNotificationIsPriorKey] boolValue]) atomic_fetch_add(&will, 1);
    else atomic_fetch_add(&did, 1);
}
@end

static void emit(id object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
}

static int threadCount(void) {
    thread_act_array_t threads;
    mach_msg_type_number_t count;
    if (task_threads(mach_task_self(), &threads, &count) != KERN_SUCCESS) return -1;
    for (mach_msg_type_number_t i = 0; i < count; i++) mach_port_deallocate(mach_task_self(), threads[i]);
    vm_deallocate(mach_task_self(), (vm_address_t)threads, sizeof(thread_t) * count);
    return (int)count;
}

static BOOL waitFor(BOOL (^condition)(void), double seconds) {
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:seconds];
    while (!condition()) {
        if ([deadline timeIntervalSinceNow] < 0) return NO;
        usleep(1000);
    }
    return YES;
}

// The sequence the detail-change check is judged on, observed on one thread,
// through the setter as callers send it (so automatic notifications count too).
static NSDictionary *detailsSequence(NSThread *thread) {
    Counter *counter = [[Counter new] autorelease];
    [thread addObserver:counter forKeyPath:@"progressDetails" options:NSKeyValueObservingOptionPrior context:NULL];
    NSMutableArray *steps = [NSMutableArray array];
    void (^act)(NSString *, void (^)(void)) = ^(NSString *label, void (^action)(void)) {
        int before = atomic_load(&counter->did);
        action();
        [steps addObject:@{@"step": label, @"notified": @(atomic_load(&counter->did) - before),
                           @"value": thread.progressDetails ?: [NSNull null]}];
    };
    void (^step)(NSString *, NSString *) = ^(NSString *label, NSString *value) {
        act(label, ^{ [thread setProgressDetails:value]; });
    };
    [thread setStatus:@"Loading"];
    step(@"same text as the status", @"Loading");
    step(@"same content, another object", [NSString stringWithFormat:@"%@", @"Loading"]);
    step(@"new text", @"Step 2");
    step(@"same text again", @"Step 2");
    step(@"nil", nil);
    step(@"nil again", nil);
    [thread setStatus:@"Step 3"];
    step(@"text equal to a later status", @"Step 3");
    // Nested operations: nil shows the details around, leaving shows them again.
    act(@"enter a nested operation", ^{ [thread enterOperation]; });
    step(@"nested: the details around it", @"Step 3");
    step(@"nested: new text", @"Nested");
    step(@"nested: nil shows the details around it", nil);
    step(@"nested: nil again", nil);
    step(@"nested: text before leaving", @"Leaving");
    act(@"leave the nested operation", ^{ [thread exitOperation]; });
    act(@"enter and leave without details", ^{ [thread enterOperation]; [thread exitOperation]; });
    [thread removeObserver:counter forKeyPath:@"progressDetails"];
    return @{@"steps": steps, @"will": @(atomic_load(&counter->will)), @"did": @(atomic_load(&counter->did))};
}

// The other keys the category notifies by hand: [notifications for a change,
// notifications for the same value again]. Run on a thread of its own, which
// ends cancelled.
static NSDictionary *keyNotifications(NSThread *thread) {
    NSMutableDictionary *counts = [NSMutableDictionary dictionary];
    void (^measure)(NSString *, void (^)(void)) = ^(NSString *key, void (^set)(void)) {
        Counter *counter = [[Counter new] autorelease];
        [thread addObserver:counter forKeyPath:key options:0 context:NULL];
        set();
        int first = atomic_load(&counter->did);
        set();
        int second = atomic_load(&counter->did) - first;
        [thread removeObserver:counter forKeyPath:key];
        counts[key] = @[@(first), @(second)];
    };
    measure(@"status", ^{ [thread setStatus:@"Probe status"]; });
    measure(@"progress", ^{ [thread setProgress:0.25]; });
    measure(@"supportsCancel", ^{ [thread setSupportsCancel:YES]; });
    measure(@"supportsBackgrounding", ^{ [thread setSupportsBackgrounding:YES]; });
    measure(@"uniqueId", ^{ [thread setUniqueId:@"probe-id"]; });
    measure(@"isCancelled", ^{ [thread setIsCancelled:YES]; });
    return counts;
}

static int contract(void) {
    NSMutableDictionary *result = [NSMutableDictionary dictionary];

    // Starts at once, off the calling thread, and hands back the thread it runs on.
    __block NSThread *inside = nil;
    __block BOOL ranOnMain = YES;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    NSThread *thread = [[NSThread performBlockInBackground:^{
        inside = [NSThread currentThread];
        ranOnMain = [NSThread isMainThread];
        dispatch_semaphore_signal(done);
    }] retain];
    result[@"returned_class_is_thread"] = @([thread isKindOfClass:[NSThread class]]);
    result[@"ran"] = @((BOOL)(dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC)) == 0));
    result[@"same_thread_object"] = @((BOOL)(inside == thread));
    result[@"ran_off_main"] = @((BOOL)!ranOnMain);
    result[@"finished"] = @(waitFor(^{ return thread.isFinished; }, 5));
    [thread release];

    // Started, not just scheduled: right after the call, is it executing (or done)?
    int notYetExecuting = 0;
    for (int i = 0; i < 300; i++) {
        @autoreleasepool {
            dispatch_semaphore_t release = dispatch_semaphore_create(0);
            NSThread *t = [NSThread performBlockInBackground:^{ dispatch_semaphore_wait(release, DISPATCH_TIME_FOREVER); }];
            if (!t.isExecuting && !t.isFinished) notYetExecuting++;
            dispatch_semaphore_signal(release);
            waitFor(^{ return t.isFinished; }, 5);
        }
    }
    result[@"not_yet_executing_right_after_start_of_300"] = @(notYetExecuting);

    // Autoreleased objects inside the block are drained with the block's pool.
    atomic_store(&deallocated, 0);
    NSThread *pooled = [[NSThread performBlockInBackground:^{
        [[Sentinel new] autorelease];
    }] retain];
    waitFor(^{ return pooled.isFinished; }, 5);
    usleep(20 * 1000);
    result[@"autoreleased_inside_block_released"] = @((BOOL)(atomic_load(&deallocated) == 1));
    [pooled release];

    // Captures: released once the block has run, while the caller still holds the thread.
    atomic_store(&deallocated, 0);
    Sentinel *captured = [Sentinel new];
    NSThread *holding = [[NSThread performBlockInBackground:^{ [captured description]; }] retain];
    [captured release];
    waitFor(^{ return holding.isFinished; }, 5);
    BOOL releasedWhileHeld = waitFor(^{ return (BOOL)(atomic_load(&deallocated) == 1); }, 1);
    result[@"captures_released_while_thread_is_held"] = @(releasedWhileHeld);
    [holding release];
    result[@"captures_released_after_thread_release"] = @(waitFor(^{ return (BOOL)(atomic_load(&deallocated) == 1); }, 2));

    // Runs to the end even when nobody keeps the returned object.
    __block atomic_int finishedUnheld = 0;
    @autoreleasepool {
        [NSThread performBlockInBackground:^{ usleep(50 * 1000); atomic_store(&finishedUnheld, 1); }];
    }
    result[@"runs_to_end_unheld"] = @(waitFor(^{ return (BOOL)(atomic_load(&finishedUnheld) == 1); }, 5));

    // An exception stays inside the thread: the process survives, the thread ends.
    NSThread *throwing = [[NSThread performBlockInBackground:^{
        [NSException raise:NSGenericException format:@"synthetic failure inside a background block"];
    }] retain];
    result[@"exception_contained"] = @(waitFor(^{ return throwing.isFinished; }, 5));
    [throwing release];

    // Cooperative cancellation, and the dictionary the block and the caller share.
    __block atomic_int sawCancel = 0;
    NSThread *cancellable = [[NSThread performBlockInBackground:^{
        NSThread *me = [NSThread currentThread];
        me.threadDictionary[@"probe"] = @"shared";
        while (!me.isCancelled) usleep(1000);
        atomic_store(&sawCancel, 1);
    }] retain];
    waitFor(^{ return (BOOL)(cancellable.threadDictionary[@"probe"] != nil); }, 5);
    result[@"thread_dictionary_shared"] = @([cancellable.threadDictionary[@"probe"] isEqual:@"shared"]);
    [cancellable cancel];
    result[@"cancel_observed"] = @(waitFor(^{ return (BOOL)(atomic_load(&sawCancel) == 1); }, 5));
    result[@"cancelled_finishes"] = @(waitFor(^{ return cancellable.isFinished; }, 5));
    [cancellable release];

    // Progress details, on a background thread and on this one.
    __block NSDictionary *background = nil;
    dispatch_semaphore_t detailsDone = dispatch_semaphore_create(0);
    [NSThread performBlockInBackground:^{
        background = [detailsSequence([NSThread currentThread]) retain];
        dispatch_semaphore_signal(detailsDone);
    }];
    dispatch_semaphore_wait(detailsDone, dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC));
    result[@"details_background"] = background ?: [NSNull null];
    result[@"details_current"] = detailsSequence([NSThread currentThread]);
    [background release];

    __block NSDictionary *keys = nil;
    dispatch_semaphore_t keysDone = dispatch_semaphore_create(0);
    [NSThread performBlockInBackground:^{
        keys = [keyNotifications([NSThread currentThread]) retain];
        dispatch_semaphore_signal(keysDone);
    }];
    dispatch_semaphore_wait(keysDone, dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC));
    result[@"key_notifications"] = keys ?: [NSNull null];
    [keys release];

    usleep(100 * 1000);
    result[@"threads_alive"] = @(threadCount());
    emit(result);
    return 0;
}

typedef NSThread *(*SpawnIMP)(id, SEL, void (^)(void));
typedef void (*DetailsIMP)(id, SEL, NSString *);

static double microseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1000.0;
}

static int interleave(const char *dylibA, const char *dylibB, int count) {
    SpawnIMP spawn[2];
    DetailsIMP details[2];
    const char *paths[2] = {dylibA, dylibB};
    for (int v = 0; v < 2; v++) {
        if (!dlopen(paths[v], RTLD_NOW | RTLD_LOCAL)) { fprintf(stderr, "dlopen %s: %s\n", paths[v], dlerror()); return 2; }
        spawn[v] = (SpawnIMP)method_getImplementation(class_getClassMethod(NSThread.class, @selector(performBlockInBackground:)));
        details[v] = (DetailsIMP)method_getImplementation(class_getInstanceMethod(NSThread.class, @selector(setProgressDetails:)));
    }
    if (spawn[0] == spawn[1]) { fprintf(stderr, "same implementation twice\n"); return 2; }
    const char *first = getenv("HOROS_AB_FIRST");
    int start = (first && strcmp(first, "B") == 0) ? 1 : 0;
    NSMutableDictionary *results[2] = {[NSMutableDictionary dictionary], [NSMutableDictionary dictionary]};
    for (int v = 0; v < 2; v++)
        for (NSString *name in @[@"start_us", @"run_to_end_us", @"details_us", @"notifications_count", @"threads_left_count"])
            results[v][name] = [NSMutableArray array];
    for (int i = 0; i < count; i++) {
        for (int slot = 0; slot < 2; slot++) {
            int v = ((i % 2 == 0) == (slot == 0)) ? start : 1 - start;
            @autoreleasepool {
                int before = threadCount();
                dispatch_semaphore_t ran = dispatch_semaphore_create(0);
                uint64_t t0 = mach_absolute_time();
                __block uint64_t reached = 0;
                NSThread *thread = spawn[v](NSThread.class, @selector(performBlockInBackground:), ^{
                    reached = mach_absolute_time();
                    dispatch_semaphore_signal(ran);
                });
                uint64_t t1 = mach_absolute_time();
                dispatch_semaphore_wait(ran, DISPATCH_TIME_FOREVER);
                [thread retain];
                waitFor(^{ return thread.isFinished; }, 5);
                [thread release];
                [results[v][@"start_us"] addObject:@(microseconds(t0, t1))];
                [results[v][@"run_to_end_us"] addObject:@(microseconds(t0, reached))];
                // Detail updates on the calling thread, observed.
                NSThread *me = [NSThread currentThread];
                Counter *counter = [[Counter new] autorelease];
                [me addObserver:counter forKeyPath:@"progressDetails" options:0 context:NULL];
                NSArray *sequence = @[@"Loading", @"Loading", @"Step 2", @"Step 2", @"Step 3"];
                uint64_t d0 = mach_absolute_time();
                for (NSString *value in sequence)
                    details[v](me, @selector(setProgressDetails:), value);
                uint64_t d1 = mach_absolute_time();
                details[v](me, @selector(setProgressDetails:), nil);
                [me removeObserver:counter forKeyPath:@"progressDetails"];
                [results[v][@"details_us"] addObject:@(microseconds(d0, d1) / sequence.count)];
                [results[v][@"notifications_count"] addObject:@(atomic_load(&counter->did))];
                usleep(2000);
                [results[v][@"threads_left_count"] addObject:@(threadCount() - before)];
            }
        }
    }
    emit(@{@"A": results[0], @"B": results[1]});
    return 0;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc >= 2 && strcmp(argv[1], "contract") == 0)
            return contract();
        if (argc >= 5 && strcmp(argv[1], "interleave") == 0)
            return interleave(argv[2], argv[3], atoi(argv[4]));
        fprintf(stderr, "usage: %s contract | interleave <A> <B> <count>\n", argv[0]);
        return 64;
    }
}
