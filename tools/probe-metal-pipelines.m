// Opening MPR and VR engines in two revisions in one process (#622), for tools/measure-object-interleaved.py.
// Each dylib holds a revision's MPR and VR engines and tools/probe-metal-pipelines-shim.swift.
//
//   probe interleave <dylib A> <dylib B>
//       sets each revision up (a 128 × 128 × 64 volume and one kept engine of each kind, which compiles what the
//       process has not compiled yet), warms every case up, and alternates the two call by call (ABBA pairs;
//       HOROS_AB_FIRST says which starts). Prints {"A": {...}, "B": {...}}, milliseconds per call:
//         mpr_engine_ms            another MPR engine
//         vr_engine_ms             another VR engine
//         mpr_open_ms              another MPR window: engine, upload, first 512 × 512 plane
//         vr_open_ms               another VR window: engine, upload, first 512 × 512 picture
//         concurrent_engines_ms    four MPR engines made at once on four threads
//         reslice_ms               a plane of the kept MPR engine
//         render_ms                a picture of the kept VR engine
//   probe first <dylib>
//       one revision in a new process: the first MPR engine and the first VR engine, the compilation included.
//       Prints {"first_engines_ms": [ms]}.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <mach/mach_time.h>

typedef struct {
    int (*device)(void);
    int (*setup)(void);
    int (*mprEngine)(void);
    int (*vrEngine)(void);
    int (*mprOpen)(void);
    int (*vrOpen)(void);
    int (*concurrent)(int);
    int (*reslice)(void);
    int (*render)(void);
} Revision;

static void *entry(void *image, const char *name, const char *path) {
    void *symbol = dlsym(image, name);
    if (!symbol) {
        fprintf(stderr, "%s lacks %s\n", path, name);
        exit(3);
    }
    return symbol;
}

static Revision load(const char *path) {
    void *image = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!image) {
        fprintf(stderr, "%s\n", dlerror());
        exit(3);
    }
    Revision revision = {entry(image, "horos_ab_pipelines_device", path), entry(image, "horos_ab_pipelines_setup", path), entry(image, "horos_ab_pipelines_mpr_engine", path),
                         entry(image, "horos_ab_pipelines_vr_engine", path), entry(image, "horos_ab_pipelines_mpr_open", path),
                         entry(image, "horos_ab_pipelines_vr_open", path), entry(image, "horos_ab_pipelines_concurrent", path),
                         entry(image, "horos_ab_pipelines_reslice", path), entry(image, "horos_ab_pipelines_render", path)};
    return revision;
}

static double milliseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1e6;
}

// One call, with the autorelease pool drained as the app's event loop drains it.
static double timed(Revision revision, int which) {
    int status = -1;
    uint64_t start = mach_absolute_time();
    @autoreleasepool {
        switch (which) {
            case 0: status = revision.mprEngine(); break;
            case 1: status = revision.vrEngine(); break;
            case 2: status = revision.mprOpen(); break;
            case 3: status = revision.vrOpen(); break;
            case 4: status = revision.concurrent(4); break;
            case 5: status = revision.reslice(); break;
            case 6: status = revision.render(); break;
        }
    }
    uint64_t end = mach_absolute_time();
    if (status != 0) {
        fprintf(stderr, "case %d failed\n", which);
        exit(5);
    }
    return milliseconds(start, end);
}

static void emit(NSDictionary *object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 4 && strcmp(argv[1], "interleave") == 0) {
            Revision revisions[2] = {load(argv[2]), load(argv[3])};
            for (int slot = 0; slot < 2; ++slot) {
                if (revisions[slot].setup() != 0) {
                    fprintf(stderr, "setup failed\n");
                    return 4;
                }
            }
            NSArray *names = @[@"mpr_engine_ms", @"vr_engine_ms", @"mpr_open_ms", @"vr_open_ms", @"concurrent_engines_ms",
                               @"reslice_ms", @"render_ms"];
            int pairs[] = {20, 20, 20, 20, 10, 40, 40};
            for (NSUInteger which = 0; which < names.count; ++which)
                for (int slot = 0; slot < 2; ++slot) timed(revisions[slot], (int)which);
            const char *first = getenv("HOROS_AB_FIRST");
            int start = first && strcmp(first, "B") == 0 ? 1 : 0;
            NSMutableDictionary *results[2] = {[NSMutableDictionary dictionary], [NSMutableDictionary dictionary]};
            for (NSUInteger which = 0; which < names.count; ++which) {
                NSMutableArray *values[2] = {[NSMutableArray array], [NSMutableArray array]};
                for (int index = 0; index < pairs[which]; ++index) {
                    for (int slot = 0; slot < 2; ++slot) {
                        int variant = ((index % 2 == 0) == (slot == 0)) ? start : 1 - start;
                        [values[variant] addObject:@(timed(revisions[variant], (int)which))];
                    }
                }
                results[0][names[which]] = values[0];
                results[1][names[which]] = values[1];
            }
            emit(@{@"A": results[0], @"B": results[1]});
            return 0;
        }
        if (argc == 3 && strcmp(argv[1], "first") == 0) {
            Revision revision = load(argv[2]);
            if (revision.device() != 0) {
                fprintf(stderr, "no Metal device\n");
                return 4;
            }
            uint64_t begin = mach_absolute_time();
            int status;
            @autoreleasepool {
                status = revision.mprEngine() | revision.vrEngine();
            }
            uint64_t end = mach_absolute_time();
            if (status != 0) {
                fprintf(stderr, "the first engines failed\n");
                return 5;
            }
            emit(@{@"first_engines_ms": @[@(milliseconds(begin, end))]});
            return 0;
        }
        fprintf(stderr, "usage: probe interleave <dylib A> <dylib B> | first <dylib>\n");
        return 2;
    }
}
