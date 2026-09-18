// The Metal volume render of two revisions in one process (#621), for tools/measure-object-interleaved.py.
// Each dylib holds a revision's VolumeMetalRenderer.swift and tools/probe-vr-render-shim.swift, which renders
// the host's frame through the renderer bridge at that revision.
//
//   probe interleave <dylib A> <dylib B>
//       gives each revision its own renderer and a synthetic 256 × 256 × 96 volume, warms every scenario up,
//       and alternates the two call by call (ABBA pairs, both rendering the same frame; HOROS_AB_FIRST says
//       which starts). Prints {"A": {...}, "B": {...}}, milliseconds per frame:
//         rotate_composite_ms   composite 512 × 512, the camera turning, one transfer function
//         rotate_mip_ms         MIP 512 × 512, the camera turning
//         rotate_large_ms       composite 1024 × 768, the camera turning
//         window_drag_ms        composite 512 × 512, the window level moving
//         preset_switch_ms      composite 512 × 512, two presets alternating every frame
//         opacity_drag_ms       composite 512 × 512, a point of the opacity curve moving
//   probe first <dylib>
//       one revision in a new process: the first composite 512 × 512 frame after the upload.
//       Prints {"first_ms": [ms]}.
//   probe memory <dylib>
//       one revision in a new process, on a 64 × 64 × 32 volume: physical footprint after the upload, after
//       200 frames of alternating presets, and the peak. Prints MiB; descriptive, not a protocol metric.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_time.h>

typedef struct {
    int (*setup)(int, int, int);
    int (*render)(int, int);
} Renderer;

static Renderer load(const char *path) {
    void *image = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!image) {
        fprintf(stderr, "%s\n", dlerror());
        exit(3);
    }
    Renderer renderer = {dlsym(image, "horos_ab_vr_setup"), dlsym(image, "horos_ab_vr_render")};
    if (!renderer.setup || !renderer.render) {
        fprintf(stderr, "%s lacks the shim's entry points\n", path);
        exit(3);
    }
    return renderer;
}

static double milliseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1e6;
}

// One frame, with the autorelease pool drained as the app's event loop drains it after each one.
static double frame(Renderer renderer, int scenario, int index) {
    int status;
    uint64_t start = mach_absolute_time();
    @autoreleasepool {
        status = renderer.render(scenario, index);
    }
    uint64_t end = mach_absolute_time();
    if (status != 0) {
        fprintf(stderr, "frame %d of scenario %d failed\n", index, scenario);
        exit(5);
    }
    return milliseconds(start, end);
}

static void prepare(Renderer renderer, int width, int height, int depth) {
    if (renderer.setup(width, height, depth) != 0) {
        fprintf(stderr, "the renderer could not be set up\n");
        exit(4);
    }
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
            Renderer renderers[2] = {load(argv[2]), load(argv[3])};
            for (int slot = 0; slot < 2; ++slot) prepare(renderers[slot], 256, 256, 96);
            for (int scenario = 0; scenario < 6; ++scenario)
                for (int warm = 0; warm < 3; ++warm)
                    for (int slot = 0; slot < 2; ++slot) frame(renderers[slot], scenario, warm);
            const char *first = getenv("HOROS_AB_FIRST");
            int start = first && strcmp(first, "B") == 0 ? 1 : 0;
            NSArray *names = @[@"rotate_composite_ms", @"rotate_mip_ms", @"rotate_large_ms", @"window_drag_ms",
                               @"preset_switch_ms", @"opacity_drag_ms"];
            int pairs[] = {40, 40, 20, 40, 40, 40};
            NSMutableDictionary *results[2] = {[NSMutableDictionary dictionary], [NSMutableDictionary dictionary]};
            for (NSUInteger scenario = 0; scenario < names.count; ++scenario) {
                NSMutableArray *values[2] = {[NSMutableArray array], [NSMutableArray array]};
                for (int index = 0; index < pairs[scenario]; ++index) {
                    for (int slot = 0; slot < 2; ++slot) {
                        int variant = ((index % 2 == 0) == (slot == 0)) ? start : 1 - start;
                        [values[variant] addObject:@(frame(renderers[variant], (int)scenario, index))];
                    }
                }
                results[0][names[scenario]] = values[0];
                results[1][names[scenario]] = values[1];
            }
            emit(@{@"A": results[0], @"B": results[1]});
            return 0;
        }
        if (argc == 3 && strcmp(argv[1], "first") == 0) {
            Renderer renderer = load(argv[2]);
            prepare(renderer, 256, 256, 96);
            emit(@{@"first_ms": @[@(frame(renderer, 0, 0))]});
            return 0;
        }
        if (argc == 3 && strcmp(argv[1], "memory") == 0) {
            Renderer renderer = load(argv[2]);
            prepare(renderer, 64, 64, 32);
            uint64_t peakBefore = 0, peakAfter = 0;
            uint64_t before = footprint(&peakBefore);
            uint64_t sampled = before;
            for (int index = 0; index < 200; ++index) {
                frame(renderer, 4, index);
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
