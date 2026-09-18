// The Metal MPR reconstruction of two revisions in one process (#620), for
// tools/measure-object-interleaved.py. Each dylib holds a revision's MPRMetalReslicer.swift and
// tools/probe-mpr-reslice-shim.swift, which does the host's work for one frame at that revision.
//
//   probe interleave <dylib A> <dylib B>
//       gives each revision its own engine and a synthetic 256 × 256 × 96 volume, warms every plane up,
//       and alternates the two call by call (ABBA pairs; HOROS_AB_FIRST says which starts). Prints
//       {"A": {...}, "B": {...}}, milliseconds per reconstruction:
//         small_single_ms   512 × 512, a single plane
//         large_single_ms   1680 × 1050, a single plane
//         small_slab_ms     512 × 512, a 20 mm maximum slab (21 samples)
//         large_slab_ms     1680 × 1050, a 20 mm mean slab
//         alternating_ms    an MPR window's three views of unequal sizes, in turn
//   probe first <dylib>
//       one revision in a new process: the first 1680 × 1050 reconstruction after the upload, the output
//       plane it makes included. Prints {"first_ms": [ms]}.
//   probe memory <dylib>
//       one revision in a new process, on a 64 × 64 × 32 volume so its upload weighs little: physical
//       footprint after the upload, after 200 reconstructions of the three views, and the peak. Prints MiB;
//       descriptive, not a protocol metric.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_time.h>

typedef struct {
    int (*setup)(int, int, int);
    int (*plane)(int, int, float, int);
    int (*reslice)(int);
} Engine;

static Engine load(const char *path) {
    void *image = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!image) {
        fprintf(stderr, "%s\n", dlerror());
        exit(3);
    }
    Engine engine = {dlsym(image, "horos_ab_mpr_setup"), dlsym(image, "horos_ab_mpr_plane"), dlsym(image, "horos_ab_mpr_reslice")};
    if (!engine.setup || !engine.plane || !engine.reslice) {
        fprintf(stderr, "%s lacks the shim's entry points\n", path);
        exit(3);
    }
    return engine;
}

enum { SmallSingle, LargeSingle, SmallSlab, LargeSlab, ViewLarge, ViewMedium, ViewSmall, PlaneCount };

static void prepare(Engine engine, int width, int height, int depth) {
    if (engine.setup(width, height, depth) != 0) {
        fprintf(stderr, "the engine could not be set up\n");
        exit(4);
    }
    int planes[PlaneCount][4] = {{512, 512, 0, 1}, {1680, 1050, 0, 1}, {512, 512, 20, 1}, {1680, 1050, 20, 3},
                                 {1680, 1050, 0, 1}, {840, 525, 0, 1}, {560, 350, 0, 1}};
    for (int index = 0; index < PlaneCount; ++index) {
        if (engine.plane(planes[index][0], planes[index][1], planes[index][2], planes[index][3]) != index) {
            fprintf(stderr, "plane %d was refused\n", index);
            exit(4);
        }
    }
}

static double milliseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1e6;
}

// One frame, with the autorelease pool drained as the app's event loop drains it after each one: the
// command buffer a reconstruction autoreleases holds its output plane, and a loop without a drain kept
// every frame's plane alive, so the baseline's allocations never came back to be reused.
static double reconstruct(Engine engine, int plane) {
    int status;
    uint64_t start = mach_absolute_time();
    @autoreleasepool {
        status = engine.reslice(plane);
    }
    uint64_t end = mach_absolute_time();
    if (status != 0) {
        fprintf(stderr, "the reconstruction of plane %d failed\n", plane);
        exit(5);
    }
    return milliseconds(start, end);
}

static void emit(NSDictionary *object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
}

static uint64_t footprint(uint64_t *peak) {
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return 0;
    if (peak) *peak = info.ledger_phys_footprint_peak;
    return info.phys_footprint;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc == 4 && strcmp(argv[1], "interleave") == 0) {
            Engine engines[2] = {load(argv[2]), load(argv[3])};
            for (int slot = 0; slot < 2; ++slot) prepare(engines[slot], 256, 256, 96);
            for (int plane = 0; plane < PlaneCount; ++plane)
                for (int warm = 0; warm < 3; ++warm)
                    for (int slot = 0; slot < 2; ++slot) reconstruct(engines[slot], plane);
            const char *first = getenv("HOROS_AB_FIRST");
            int start = first && strcmp(first, "B") == 0 ? 1 : 0;
            NSArray *names = @[@"small_single_ms", @"large_single_ms", @"small_slab_ms", @"large_slab_ms", @"alternating_ms"];
            int pairs[] = {60, 40, 40, 20, 60};
            NSMutableDictionary *results[2] = {[NSMutableDictionary dictionary], [NSMutableDictionary dictionary]};
            for (NSUInteger metric = 0; metric < names.count; ++metric) {
                NSMutableArray *values[2] = {[NSMutableArray array], [NSMutableArray array]};
                for (int index = 0; index < pairs[metric]; ++index) {
                    int plane = metric < 4 ? (int)metric : ViewLarge + index % 3;
                    for (int slot = 0; slot < 2; ++slot) {
                        int variant = ((index % 2 == 0) == (slot == 0)) ? start : 1 - start;
                        [values[variant] addObject:@(reconstruct(engines[variant], plane))];
                    }
                }
                results[0][names[metric]] = values[0];
                results[1][names[metric]] = values[1];
            }
            emit(@{@"A": results[0], @"B": results[1]});
            return 0;
        }
        if (argc == 3 && strcmp(argv[1], "first") == 0) {
            Engine engine = load(argv[2]);
            prepare(engine, 256, 256, 96);
            emit(@{@"first_ms": @[@(reconstruct(engine, LargeSingle))]});
            return 0;
        }
        if (argc == 3 && strcmp(argv[1], "memory") == 0) {
            Engine engine = load(argv[2]);
            prepare(engine, 64, 64, 32);
            uint64_t peakBefore = 0, peakAfter = 0;
            uint64_t before = footprint(&peakBefore);
            uint64_t sampled = before;
            for (int index = 0; index < 200; ++index) {
                reconstruct(engine, ViewLarge + index % 3);
                uint64_t now = footprint(NULL);
                if (now > sampled) sampled = now;
            }
            uint64_t after = footprint(&peakAfter);
            double mib = 1024.0 * 1024.0;
            emit(@{@"after_upload_mib": @(before / mib), @"after_200_mib": @(after / mib),
                   @"retained_growth_mib": @(((double)after - (double)before) / mib),
                   @"sampled_peak_growth_mib": @(((double)sampled - (double)before) / mib),
                   @"ledger_peak_before_mib": @(peakBefore / mib), @"ledger_peak_after_mib": @(peakAfter / mib)});
            return 0;
        }
        fprintf(stderr, "usage: probe interleave <dylib A> <dylib B> | first <dylib> | memory <dylib>\n");
        return 2;
    }
}
