// Loads images with the app's own DCMPix from inside the development app (#630),
// injected with DYLD_INSERT_LIBRARIES, and records what each load produced and
// how long it took.
//
//   HOROS_DCMPIX_PLAN     a JSON file: {"images": [{"path", "frame", "width", "height",
//                         "samples": [[x, y, value], ...]}], "broken": [paths],
//                         "replace": {"path", "with", "width", "height", "samples"}}
//   HOROS_DCMPIX_TRIGGER  a path: run once that file exists
//   HOROS_DCMPIX_LOG      a JSON lines file, one line per load and one summary
//
// Phases, in order:
//   cold        every image once, DCMPix created and loaded one after the other
//   warm        every image again while the cold DCMPix of the same file is still
//               alive, so the parsed file comes from the shared cache
//   concurrent  every image loaded by 8 threads at once (the viewers' pattern)
//   purge       all DCMPix released, +purgeCachedDictionaries, three cycles of
//               load-all / release / purge
//   replace     a DCMPix of a file stays alive while the file is replaced on disk;
//               a new DCMPix of the same path must read the new pixels (#603)
//   broken      truncated or invalid files: the load must fail without a crash
//
// Each load reports its time, whether the DCMPix produced pixels, its size, and
// whether the sampled pixels match the plan.
//
//   xcrun clang -dynamiclib -fobjc-arc -framework Cocoa tools/probe-dcmpix-load.m -o probe-dcmpix-load.dylib
#import <Cocoa/Cocoa.h>
#include <mach/mach_time.h>

@interface NSObject (DCMPixLoadProbe)
- (id)initWithPath:(NSString *)s :(long)pos :(long)tot :(float *)ptr :(long)f :(long)ss isBonjour:(BOOL)hello imageObj:(id)iO;
- (void)CheckLoad;
- (float *)fImage;
- (long)pwidth;
- (long)pheight;
+ (void)purgeCachedDictionaries;
@end

static NSString *logPath;
static NSLock *logLock;

static void writeLine(NSDictionary *object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    [logLock lock];
    NSFileHandle *handle = [NSFileHandle fileHandleForWritingAtPath:logPath];
    if (!handle) {
        [[NSData data] writeToFile:logPath atomically:NO];
        handle = [NSFileHandle fileHandleForWritingAtPath:logPath];
    }
    [handle seekToEndOfFile];
    [handle writeData:data];
    [handle writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
    [handle closeFile];
    [logLock unlock];
}

static double microseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1000.0;
}

// One DCMPix loaded and judged against the plan; the object is returned alive.
static id loadOne(NSDictionary *entry, NSString *phase, NSMutableDictionary *line) {
    Class pixClass = NSClassFromString(@"DCMPix");
    uint64_t t0 = mach_absolute_time();
    id pix = [[pixClass alloc] initWithPath:entry[@"path"] :0 :1 :NULL :[entry[@"frame"] longValue] :0 isBonjour:NO imageObj:nil];
    [pix CheckLoad];
    uint64_t t1 = mach_absolute_time();
    float *pixels = pix ? [pix fImage] : NULL;
    long width = pix ? [pix pwidth] : 0, height = pix ? [pix pheight] : 0;
    BOOL samplesMatch = pixels != NULL && entry[@"samples"] != nil;
    for (NSArray *sample in entry[@"samples"]) {
        long x = [sample[0] longValue], y = [sample[1] longValue];
        if (x >= width || y >= height || fabs(pixels[y * width + x] - [sample[2] doubleValue]) > 0.5) {
            samplesMatch = NO;
            break;
        }
    }
    [line addEntriesFromDictionary:@{@"phase": phase, @"path": [entry[@"path"] lastPathComponent], @"us": @(microseconds(t0, t1)),
                                     @"pixels": @(pixels != NULL), @"width": @(width), @"height": @(height),
                                     @"size_ok": @(width == [entry[@"width"] longValue] && height == [entry[@"height"] longValue]),
                                     @"samples_ok": @(samplesMatch)}];
    return pix;
}

static void run(NSDictionary *plan) {
    NSArray *images = plan[@"images"];
    NSMutableDictionary *summary = [NSMutableDictionary dictionary];
    uint64_t start = mach_absolute_time();

    // cold, then warm while the cold ones are alive
    NSMutableArray *alive = [NSMutableArray array];
    for (NSDictionary *entry in images) {
        @autoreleasepool {
            NSMutableDictionary *line = [NSMutableDictionary dictionary];
            id pix = loadOne(entry, @"cold", line);
            if (pix) [alive addObject:pix];
            writeLine(line);
        }
    }
    NSMutableArray *warm = [NSMutableArray array];
    for (NSDictionary *entry in images) {
        @autoreleasepool {
            NSMutableDictionary *line = [NSMutableDictionary dictionary];
            id pix = loadOne(entry, @"warm", line);
            if (pix) [warm addObject:pix];
            writeLine(line);
        }
    }
    [warm removeAllObjects];
    [alive removeAllObjects];

    // concurrent: 8 threads, every image once
    uint64_t c0 = mach_absolute_time();
    dispatch_apply(8, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^(size_t worker) {
        for (NSUInteger index = worker; index < images.count; index += 8) {
            @autoreleasepool {
                NSMutableDictionary *line = [NSMutableDictionary dictionary];
                id pix = loadOne(images[index], @"concurrent", line);
                (void)pix;
                writeLine(line);
            }
        }
    });
    summary[@"concurrent_wall_ms"] = @(microseconds(c0, mach_absolute_time()) / 1000.0);

    // purge cycles
    NSMutableArray *purges = [NSMutableArray array];
    for (int cycle = 0; cycle < 3; cycle++) {
        @autoreleasepool {
            NSMutableArray *held = [NSMutableArray array];
            for (NSDictionary *entry in images) {
                NSMutableDictionary *line = [NSMutableDictionary dictionary];
                id pix = loadOne(entry, @"purge-cycle", line);
                if (pix) [held addObject:pix];
                writeLine(line);
            }
            [held removeAllObjects];
        }
        uint64_t p0 = mach_absolute_time();
        [NSClassFromString(@"DCMPix") purgeCachedDictionaries];
        [purges addObject:@(microseconds(p0, mach_absolute_time()))];
    }
    summary[@"purge_us"] = purges;

    // replace (#603)
    NSDictionary *replace = plan[@"replace"];
    if (replace) {
        @autoreleasepool {
            NSDictionary *before = @{@"path": replace[@"path"], @"frame": @0, @"width": replace[@"width_before"] ?: @0,
                                     @"height": replace[@"height_before"] ?: @0, @"samples": replace[@"samples_before"] ?: @[]};
            NSMutableDictionary *first = [NSMutableDictionary dictionary];
            id kept = loadOne(before, @"replace-before", first);
            writeLine(first);
            NSString *staging = [replace[@"path"] stringByAppendingString:@".replacing"];
            [NSFileManager.defaultManager removeItemAtPath:staging error:NULL];
            [NSFileManager.defaultManager copyItemAtPath:replace[@"with"] toPath:staging error:NULL];
            rename(staging.fileSystemRepresentation, [replace[@"path"] fileSystemRepresentation]);
            NSMutableDictionary *second = [NSMutableDictionary dictionary];
            NSDictionary *after = @{@"path": replace[@"path"], @"frame": @0, @"width": replace[@"width"], @"height": replace[@"height"],
                                    @"samples": replace[@"samples"]};
            id fresh = loadOne(after, @"replace-after", second);
            writeLine(second);
            (void)kept; (void)fresh;
        }
    }

    // broken files
    for (NSString *path in plan[@"broken"]) {
        @autoreleasepool {
            NSMutableDictionary *line = [NSMutableDictionary dictionary];
            loadOne(@{@"path": path, @"frame": @0, @"width": @-1, @"height": @-1}, @"broken", line);
            writeLine(line);
        }
    }

    summary[@"total_ms"] = @(microseconds(start, mach_absolute_time()) / 1000.0);
    writeLine(@{@"summary": summary});
}

__attribute__((constructor)) static void installDCMPixLoadProbe(void) {
    NSDictionary *environment = NSProcessInfo.processInfo.environment;
    NSString *planPath = environment[@"HOROS_DCMPIX_PLAN"], *trigger = environment[@"HOROS_DCMPIX_TRIGGER"];
    logPath = environment[@"HOROS_DCMPIX_LOG"];
    if (!planPath || !trigger || !logPath) return;
    logLock = [NSLock new];
    unsetenv("DYLD_INSERT_LIBRARIES");
    writeLine(@{@"probe": @"loaded"});
    [NSNotificationCenter.defaultCenter addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil
                                                     queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        [NSThread detachNewThreadWithBlock:^{
            @autoreleasepool {
                for (int wait = 0; wait < 3000 && ![NSFileManager.defaultManager fileExistsAtPath:trigger]; wait++)
                    usleep(100000);
                NSDictionary *plan = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:planPath] options:0 error:NULL];
                @try {
                    run(plan);
                } @catch (NSException *e) {
                    writeLine(@{@"summary": @{@"exception": [NSString stringWithFormat:@"%@: %@", e.name, e.reason]}});
                }
            }
        }];
    }];
}
