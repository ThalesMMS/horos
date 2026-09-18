// Drives N2DirectoryEnumerator (#627) from linked objects: the application's
// N2DirectoryEnumerator.o, or the same source recompiled at another revision.
//
//   probe list <root> <filesOnly 0|1> <recursive 0|1> <max>
//       every path in enumeration order, the open descriptors before, after
//       enumerating and after releasing, and the threads created meanwhile
//   probe abandon <root> <entries>
//       reads a few entries, releases the enumerator: descriptors and threads
//   probe skip <root> <name>
//       calls -skipDescendants when an entry with that last component comes out
//   probe interleave <root> <scans>
//       both implementations in one process - the baseline object compiled with
//       -DN2DirectoryEnumerator=N2DirectoryEnumeratorBaseline - alternated scan
//       by scan (ABBA; HOROS_AB_FIRST says which starts) over trees prepared
//       under <root>; prints {"A": {...}, "B": {...}}
//
// Threads are counted with the pthread introspection hook, which sees every
// creation in the process, including the short-lived closedir threads the
// enumerator used to start. Built without ARC, like the object it links.
#import <Foundation/Foundation.h>
#include <fcntl.h>
#include <mach/mach_time.h>
#include <pthread/introspection.h>
#include <pthread/qos.h>
#include <stdatomic.h>
#include <sys/resource.h>

@interface ProbeEnumerator : NSEnumerator
- (id)initWithPath:(NSString *)path maxNumberOfFiles:(NSInteger)n;
- (void)setFilesOnly:(BOOL)value;
- (void)setRecursive:(BOOL)value;
- (void)skipDescendants;
@end

static atomic_int createdThreads = 0;
static pthread_introspection_hook_t previousHook;

static void countThreads(unsigned int event, pthread_t thread, void *addr, size_t size) {
    if (event == PTHREAD_INTROSPECTION_THREAD_CREATE)
        atomic_fetch_add(&createdThreads, 1);
    if (previousHook) previousHook(event, thread, addr, size);
}

static int openDescriptors(void) {
    int count = 0;
    struct rlimit limit;
    getrlimit(RLIMIT_NOFILE, &limit);
    int top = limit.rlim_cur > 4096 ? 4096 : (int)limit.rlim_cur;
    for (int fd = 0; fd < top; fd++)
        if (fcntl(fd, F_GETFD) != -1) count++;
    return count;
}

static void emit(id object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
}

static double microseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1000.0;
}

// Releasing threads start asynchronously: give them a moment to be counted.
static void settle(void) { usleep(200 * 1000); }

// Before each timed operation of the interleaved comparison (campaign 2 of
// #627), the same 20 ms of busy work for both variants. Two things used to run
// into a measurement: the closedir threads an earlier operation of the revision
// before #627 started, which finish during this work instead; and the state the
// earlier operation left the processor in - hundreds of threads wake cores and
// raise their performance state, a single-threaded scan does not, and the next
// timing inherits either. A pause instead of work made every timing start from
// an idle processor, far noisier. The closedir threads' own work is left out of
// the baseline's timings, which can only favour the baseline.
static void settleThreads(void) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    uint64_t end = mach_absolute_time() + 20ull * 1000 * 1000 * timebase.denom / timebase.numer;
    volatile uint64_t spins = 0;
    while (mach_absolute_time() < end) spins++;
}

static Class enumeratorClass(const char *name) {
    Class type = NSClassFromString(@(name));
    if (!type) { fprintf(stderr, "no class %s\n", name); exit(2); }
    return type;
}

static int list(NSString *root, BOOL filesOnly, BOOL recursive, NSInteger max) {
    Class type = enumeratorClass("N2DirectoryEnumerator");
    int before = openDescriptors();
    atomic_store(&createdThreads, 0);
    NSMutableArray *paths = [NSMutableArray array];
    int afterEnumeration;
    @autoreleasepool {
        ProbeEnumerator *enumerator = [[type alloc] initWithPath:root maxNumberOfFiles:max];
        [enumerator setFilesOnly:filesOnly];
        [enumerator setRecursive:recursive];
        NSString *path;
        while ((path = [enumerator nextObject]))
            [paths addObject:path];
        afterEnumeration = openDescriptors();
        [enumerator release];
    }
    settle();
    emit(@{@"paths": paths, @"fds_before": @(before), @"fds_after_enumeration": @(afterEnumeration),
           @"fds_after_release": @(openDescriptors()), @"threads_created": @(atomic_load(&createdThreads))});
    return 0;
}

static int abandon(NSString *root, NSInteger entries) {
    Class type = enumeratorClass("N2DirectoryEnumerator");
    int before = openDescriptors();
    atomic_store(&createdThreads, 0);
    int during;
    NSMutableArray *read = [NSMutableArray array];
    @autoreleasepool {
        ProbeEnumerator *enumerator = [[type alloc] initWithPath:root maxNumberOfFiles:-1];
        for (NSInteger i = 0; i < entries; i++) {
            NSString *path = [enumerator nextObject];
            if (!path) break;
            [read addObject:path];
        }
        during = openDescriptors();
        [enumerator release];
    }
    settle();
    emit(@{@"read": read, @"fds_before": @(before), @"fds_while_open": @(during),
           @"fds_after_release": @(openDescriptors()), @"threads_created": @(atomic_load(&createdThreads))});
    return 0;
}

static int skip(NSString *root, NSString *name) {
    Class type = enumeratorClass("N2DirectoryEnumerator");
    int before = openDescriptors();
    NSMutableArray *paths = [NSMutableArray array];
    @autoreleasepool {
        ProbeEnumerator *enumerator = [[type alloc] initWithPath:root maxNumberOfFiles:-1];
        NSString *path;
        while ((path = [enumerator nextObject])) {
            [paths addObject:path];
            if ([path.lastPathComponent isEqualToString:name])
                [enumerator skipDescendants];
        }
        [enumerator release];
    }
    settle();
    emit(@{@"paths": paths, @"fds_before": @(before), @"fds_after_release": @(openDescriptors())});
    return 0;
}

static NSArray *makeTrees(NSString *root) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSData *payload = [NSMutableData dataWithLength:512];
    NSString *wide = [root stringByAppendingPathComponent:@"wide"];
    [fm createDirectoryAtPath:wide withIntermediateDirectories:YES attributes:nil error:NULL];
    for (int i = 0; i < 4000; i++)
        [payload writeToFile:[wide stringByAppendingPathComponent:[NSString stringWithFormat:@"image-%04d.dcm", i]] atomically:NO];
    NSString *deep = [root stringByAppendingPathComponent:@"deep"];
    NSString *level = deep;
    for (int d = 0; d < 64; d++) {
        level = [level stringByAppendingPathComponent:[NSString stringWithFormat:@"series-%02d", d]];
        [fm createDirectoryAtPath:level withIntermediateDirectories:YES attributes:nil error:NULL];
        for (int i = 0; i < 4; i++)
            [payload writeToFile:[level stringByAppendingPathComponent:[NSString stringWithFormat:@"%d.dcm", i]] atomically:NO];
    }
    NSString *folders = [root stringByAppendingPathComponent:@"folders"];
    for (int f = 0; f < 800; f++) {
        NSString *folder = [folders stringByAppendingPathComponent:[NSString stringWithFormat:@"study-%03d", f]];
        [fm createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:NULL];
        for (int i = 0; i < 5; i++)
            [payload writeToFile:[folder stringByAppendingPathComponent:[NSString stringWithFormat:@"%d.dcm", i]] atomically:NO];
    }
    return @[wide, deep, folders];
}

static NSUInteger scanAll(Class type, NSString *path) {
    NSUInteger count = 0;
    @autoreleasepool {
        ProbeEnumerator *enumerator = [[type alloc] initWithPath:path maxNumberOfFiles:-1];
        while ([enumerator nextObject]) count++;
        [enumerator release];
    }
    return count;
}

static int interleave(NSString *root, int scans) {
    Class types[2] = {enumeratorClass("N2DirectoryEnumeratorBaseline"), enumeratorClass("N2DirectoryEnumerator")};
    const char *first = getenv("HOROS_AB_FIRST");
    int start = (first && strcmp(first, "B") == 0) ? 1 : 0;
    // The trees are built once per campaign and reused by every invocation: an
    // invocation is then a few seconds, and a campaign can afford many rounds -
    // what narrows the p95 when slow scans cluster in a few rounds (campaign 3).
    NSString *work = [root stringByAppendingPathComponent:@"enumerator-trees"];
    NSString *complete = [work stringByAppendingPathComponent:@"complete"];
    NSArray *trees = nil;
    if ([NSFileManager.defaultManager fileExistsAtPath:complete])
        trees = @[[work stringByAppendingPathComponent:@"wide"], [work stringByAppendingPathComponent:@"deep"],
                  [work stringByAppendingPathComponent:@"folders"]];
    else {
        [NSFileManager.defaultManager removeItemAtPath:work error:NULL];
        trees = makeTrees(work);
        [[NSData data] writeToFile:complete atomically:YES];
    }
    NSArray *names = @[@"wide_ms", @"deep_ms", @"folders_ms"];
    NSMutableDictionary *results[2] = {[NSMutableDictionary dictionary], [NSMutableDictionary dictionary]};
    NSUInteger expected[3] = {0, 0, 0};
    for (int v = 0; v < 2; v++) {
        for (NSString *name in names) results[v][name] = [NSMutableArray array];
        for (NSString *name in @[@"first_us", @"abandon_us"]) results[v][name] = [NSMutableArray array];
        results[v][@"threads_created_count"] = [NSMutableArray array];
    }
    for (int t = 0; t < 3; t++) expected[t] = scanAll(types[1], trees[t]);
    settle();
    for (int i = 0; i < scans; i++) {
        for (int slot = 0; slot < 2; slot++) {
            int v = ((i % 2 == 0) == (slot == 0)) ? start : 1 - start;
            int threadsBefore = atomic_load(&createdThreads);
            for (int t = 0; t < 3; t++) {
                settleThreads();
                uint64_t t0 = mach_absolute_time();
                NSUInteger count = scanAll(types[v], trees[t]);
                uint64_t t1 = mach_absolute_time();
                if (count != expected[t]) { fprintf(stderr, "variant %d listed %lu of %lu\n", v, count, expected[t]); return 3; }
                [results[v][names[t]] addObject:@(microseconds(t0, t1) / 1000.0)];
            }
            @autoreleasepool {
                settleThreads();
                uint64_t t0 = mach_absolute_time();
                ProbeEnumerator *enumerator = [[types[v] alloc] initWithPath:trees[0] maxNumberOfFiles:-1];
                [enumerator nextObject];
                uint64_t t1 = mach_absolute_time();
                [enumerator release];
                [results[v][@"first_us"] addObject:@(microseconds(t0, t1))];
                settleThreads();
                t0 = mach_absolute_time();
                enumerator = [[types[v] alloc] initWithPath:trees[1] maxNumberOfFiles:-1];
                for (int k = 0; k < 200; k++) [enumerator nextObject];
                [enumerator release];
                t1 = mach_absolute_time();
                [results[v][@"abandon_us"] addObject:@(microseconds(t0, t1))];
            }
            // Threads are counted when they are created, inside the scans: the count is
            // complete here without waiting (the 200 ms pause that used to stand here
            // only lengthened the invocations).
            [results[v][@"threads_created_count"] addObject:@(atomic_load(&createdThreads) - threadsBefore)];
        }
    }
    emit(@{@"A": results[0], @"B": results[1]});
    return 0;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        previousHook = pthread_introspection_hook_install(countThreads);
        if (argc >= 6 && strcmp(argv[1], "list") == 0)
            return list(@(argv[2]), atoi(argv[3]), atoi(argv[4]), atol(argv[5]));
        if (argc >= 4 && strcmp(argv[1], "abandon") == 0)
            return abandon(@(argv[2]), atol(argv[3]));
        if (argc >= 4 && strcmp(argv[1], "skip") == 0)
            return skip(@(argv[2]), @(argv[3]));
        if (argc >= 4 && strcmp(argv[1], "interleave") == 0) {
            // Comparison 2 of #627: at the default quality of service a scan ran on a
            // performance or an efficiency core from one scan to the next - the two
            // copies of the baseline differed by ±20-45 % round by round, about the
            // 1.4 times between the two kinds of core - so the scans run at the
            // quality of service of interactive work, which the scheduler keeps on
            // the performance cores.
            pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
            return interleave(@(argv[2]), atoi(argv[3]));
        }
        fprintf(stderr, "usage: %s list|abandon|skip|interleave ...\n", argv[0]);
        return 64;
    }
}
