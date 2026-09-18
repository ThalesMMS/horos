// Drives -[NSImage imageByScalingProportionallyToSize:] (#625) from linked
// objects: the application's NSImage+N2.o, or the same source at another revision.
//
//   probe contract
//       one JSON object: for each synthetic source and target, the output's
//       point size, pixel size, bits, colour model, the bounding box of its
//       opaque pixels and sampled pixel values, plus invalid inputs, lifetime
//       after the pool is drained, and serial-versus-concurrent identity
//   probe interleave <dylib A> <dylib B> <rounds>
//       both revisions as dylibs in this process, alternated call by call
//       (ABBA; HOROS_AB_FIRST says which starts); prints {"A": ..., "B": ...}
//   probe first <dylib>
//       the first conversion of a process, Core Image and AppKit set-up included
//   probe memory <dylib> <frames>
//       footprint and malloc use across a long export in one process: peak and retained
//
// Sources are built the way DCMPix builds its images - one 8-bit bitmap
// representation, grey or RGB, size in points equal to its pixels - plus an
// RGBA source, a Retina source (two pixels per point) and a Display P3 one.
// Each carries a quadrant pattern with an orientation mark in the top-left.
// Built without ARC, like the object it links.
#import <Cocoa/Cocoa.h>
#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <malloc/malloc.h>
#include <objc/runtime.h>

@interface NSImage (N2ScalingProbe)
- (NSImage *)imageByScalingProportionallyToSize:(NSSize)targetSize;
@end

// NSImage+N2.o also holds the toolbar icon helper, which names this Swift class
// of the app; the scaling path never reaches it.
@interface HorosToolbarImage : NSObject
@end
@implementation HorosToolbarImage
@end

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

// Quadrants: top-left 40, top-right 120, bottom-left 200, bottom-right 250 (grey)
// or four distinct colours; a 20 % square mark at the very top-left corner is 0.
static NSImage *source(NSString *kind, int width, int height) {
    BOOL grey = [kind isEqualToString:@"grey"];
    BOOL alpha = [kind isEqualToString:@"rgba"];
    BOOL retina = [kind isEqualToString:@"retina"];
    BOOL p3 = [kind isEqualToString:@"p3"];
    int samples = grey ? 1 : (alpha ? 4 : 3);
    NSBitmapImageRep *rep = [[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:width pixelsHigh:height
        bitsPerSample:8 samplesPerPixel:samples hasAlpha:alpha isPlanar:NO
        colorSpaceName:grey ? NSCalibratedWhiteColorSpace : NSCalibratedRGBColorSpace
        bytesPerRow:width * samples bitsPerPixel:8 * samples] autorelease];
    if (p3) rep = [rep bitmapImageRepByRetaggingWithColorSpace:[NSColorSpace displayP3ColorSpace]];
    unsigned char *pixels = rep.bitmapData;
    static const unsigned char colours[4][4] = {{220, 30, 40, 255}, {30, 200, 60, 255}, {40, 60, 210, 255}, {230, 210, 40, 255}};
    static const unsigned char greys[4] = {40, 120, 200, 250};
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int quadrant = (y >= height / 2 ? 2 : 0) + (x >= width / 2 ? 1 : 0);
            BOOL mark = x < width / 5 && y < height / 5;
            unsigned char *p = pixels + (y * width + x) * samples;
            if (grey) { p[0] = mark ? 0 : greys[quadrant]; continue; }
            unsigned char a = alpha ? (unsigned char)(x < width / 2 ? 255 : 128) : 255;
            // The representation stores premultiplied colour, as AppKit's default format does.
            for (int c = 0; c < 3; c++) p[c] = mark ? 0 : (unsigned char)(colours[quadrant][c] * a / 255);
            if (alpha) p[3] = a;
        }
    }
    NSImage *image = [[[NSImage alloc] initWithSize:retina ? NSMakeSize(width / 2.0, height / 2.0) : NSMakeSize(width, height)] autorelease];
    rep.size = image.size;
    [image addRepresentation:rep];
    return image;
}

static NSBitmapImageRep *bitmap(NSImage *image) {
    NSRect rect = NSMakeRect(0, 0, image.size.width, image.size.height);
    CGImageRef cg = [image CGImageForProposedRect:&rect context:nil hints:@{NSImageHintCTM: [NSAffineTransform transform]}];
    return cg ? [[[NSBitmapImageRep alloc] initWithCGImage:cg] autorelease] : nil;
}

// A pixel's colour samples followed by its alpha (255 without one), whatever the
// representation's layout - AppKit hands back alpha first or last depending on
// where the bitmap came from, and a TIFF round trip changes it.
static NSInteger canonicalPixel(NSBitmapImageRep *rep, NSInteger x, NSInteger y, NSUInteger *out) {
    NSUInteger raw[8] = {0};
    [rep getPixel:raw atX:x y:y];
    BOOL alpha = rep.hasAlpha, first = (rep.bitmapFormat & NSBitmapFormatAlphaFirst) != 0;
    NSInteger colours = rep.samplesPerPixel - (alpha ? 1 : 0);
    NSInteger offset = alpha && first ? 1 : 0;
    NSUInteger maximum = (1u << rep.bitsPerSample) - 1;
    for (NSInteger c = 0; c < colours; c++) out[c] = raw[offset + c] * 255 / maximum;
    out[colours] = alpha ? raw[first ? 0 : rep.samplesPerPixel - 1] * 255 / maximum : 255;
    return colours;
}

// Pixel at a fraction of the output, read in the output's own colour space.
static NSArray *sample(NSBitmapImageRep *rep, double fx, double fy) {
    NSInteger x = MIN(rep.pixelsWide - 1, (NSInteger)(fx * rep.pixelsWide));
    NSInteger y = MIN(rep.pixelsHigh - 1, (NSInteger)(fy * rep.pixelsHigh));
    NSUInteger values[8] = {0};
    NSInteger colours = canonicalPixel(rep, x, y, values);
    NSMutableArray *result = [NSMutableArray array];
    for (NSInteger i = 0; i <= colours; i++) [result addObject:@(values[i])];
    return result;
}

static NSDictionary *opaqueBox(NSBitmapImageRep *rep) {
    if (!rep.hasAlpha) return @{@"x": @0, @"y": @0, @"width": @(rep.pixelsWide), @"height": @(rep.pixelsHigh)};
    NSInteger minX = NSIntegerMax, minY = NSIntegerMax, maxX = -1, maxY = -1;
    NSUInteger values[8];
    for (NSInteger y = 0; y < rep.pixelsHigh; y++)
        for (NSInteger x = 0; x < rep.pixelsWide; x++) {
            NSInteger colours = canonicalPixel(rep, x, y, values);
            if (values[colours] > 0) {
                minX = MIN(minX, x); maxX = MAX(maxX, x); minY = MIN(minY, y); maxY = MAX(maxY, y);
            }
        }
    if (maxX < 0) return @{@"x": @0, @"y": @0, @"width": @0, @"height": @0};
    return @{@"x": @(minX), @"y": @(minY), @"width": @(maxX - minX + 1), @"height": @(maxY - minY + 1)};
}

// Every colour sample of every pixel equal, whatever the alpha layout.
static BOOL sameColours(NSImage *a, NSImage *b) {
    NSBitmapImageRep *ra = bitmap(a), *rb = bitmap(b);
    if (!ra || !rb || ra.pixelsWide != rb.pixelsWide || ra.pixelsHigh != rb.pixelsHigh) return NO;
    NSUInteger va[8], vb[8];
    for (NSInteger y = 0; y < ra.pixelsHigh; y++)
        for (NSInteger x = 0; x < ra.pixelsWide; x++) {
            NSInteger colours = canonicalPixel(ra, x, y, va);
            if (canonicalPixel(rb, x, y, vb) != colours) return NO;
            for (NSInteger c = 0; c < colours; c++) if (va[c] != vb[c]) return NO;
        }
    return YES;
}

static NSDictionary *describe(NSImage *output) {
    if (!output) return @{@"nil": @YES};
    NSBitmapImageRep *rep = bitmap(output);
    if (!rep) return @{@"nil": @NO, @"bitmap": @NO};
    NSDictionary *box = opaqueBox(rep);
    // Fractions inside the opaque content: quadrant centres and the orientation mark.
    double bx = [box[@"x"] doubleValue] / rep.pixelsWide, by = [box[@"y"] doubleValue] / rep.pixelsHigh;
    double bw = [box[@"width"] doubleValue] / rep.pixelsWide, bh = [box[@"height"] doubleValue] / rep.pixelsHigh;
    NSDictionary *samples = @{
        @"mark": sample(rep, bx + bw * 0.08, by + bh * 0.08),
        @"topLeft": sample(rep, bx + bw * 0.35, by + bh * 0.3),
        @"topRight": sample(rep, bx + bw * 0.75, by + bh * 0.25),
        @"bottomLeft": sample(rep, bx + bw * 0.25, by + bh * 0.75),
        @"bottomRight": sample(rep, bx + bw * 0.75, by + bh * 0.75),
    };
    return @{@"nil": @NO, @"points": @[@(output.size.width), @(output.size.height)],
             @"pixels": @[@(rep.pixelsWide), @(rep.pixelsHigh)], @"bits": @(rep.bitsPerSample),
             @"samples_per_pixel": @(rep.samplesPerPixel), @"alpha": @(rep.hasAlpha),
             @"model": @(rep.colorSpace.colorSpaceModel), @"colour_space": rep.colorSpace.localizedName ?: @"",
             @"opaque": box, @"values": samples};
}

typedef NSImage *(*ScaleIMP)(id, SEL, NSSize);

static int contract(void) {
    NSMutableDictionary *result = [NSMutableDictionary dictionary];
    NSMutableArray *cases = [NSMutableArray array];
    NSArray *plan = @[
        @[@"grey", @512, @512, @256, @256], @[@"grey", @512, @512, @512, @512], @[@"grey", @256, @256, @640, @640],
        @[@"grey", @512, @256, @300, @300], @[@"grey", @256, @512, @300, @300], @[@"grey", @400, @300, @100.5, @50.25],
        @[@"rgb", @640, @480, @320, @240], @[@"rgb", @640, @480, @640, @480], @[@"rgb", @300, @600, @200, @200],
        @[@"rgba", @400, @400, @200, @200], @[@"retina", @800, @600, @400, @300], @[@"retina", @800, @600, @200, @200],
        @[@"p3", @500, @500, @250, @250],
    ];
    for (NSArray *entry in plan) {
        @autoreleasepool {
            NSImage *input = source(entry[0], [entry[1] intValue], [entry[2] intValue]);
            NSSize target = NSMakeSize([entry[3] doubleValue], [entry[4] doubleValue]);
            NSImage *output = [input imageByScalingProportionallyToSize:target];
            [cases addObject:@{@"source": entry[0], @"source_points": @[@(input.size.width), @(input.size.height)],
                               @"source_pixels": @[entry[1], entry[2]], @"target": @[entry[3], entry[4]],
                               @"output": describe(output), @"input": describe(input),
                               @"identical_colours": @((BOOL)(output != nil && sameColours(input, output)))}];
        }
    }
    result[@"cases"] = cases;

    NSMutableDictionary *invalid = [NSMutableDictionary dictionary];
    NSImage *valid = source(@"grey", 64, 64);
    NSDictionary *sizes = @{@"zero": [NSValue valueWithSize:NSMakeSize(0, 10)], @"negative": [NSValue valueWithSize:NSMakeSize(-5, 10)],
                            @"nan": [NSValue valueWithSize:NSMakeSize(NAN, 10)], @"infinite": [NSValue valueWithSize:NSMakeSize(INFINITY, 10)],
                            @"huge": [NSValue valueWithSize:NSMakeSize(100000, 100000)]};
    for (NSString *name in sizes) {
        @try {
            invalid[name] = @((BOOL)([valid imageByScalingProportionallyToSize:[sizes[name] sizeValue]] == nil));
        } @catch (NSException *e) {
            invalid[name] = [@"exception: " stringByAppendingString:e.reason ?: @""];
        }
    }
    @try {
        invalid[@"empty_image"] = @((BOOL)([[[[NSImage alloc] init] autorelease] imageByScalingProportionallyToSize:NSMakeSize(10, 10)] == nil));
    } @catch (NSException *e) {
        invalid[@"empty_image"] = [@"exception: " stringByAppendingString:e.reason ?: @""];
    }
    result[@"invalid_returns_nil"] = invalid;

    // The result must stand on its own once the source and the pool are gone.
    NSImage *kept = nil;
    @autoreleasepool {
        kept = [[source(@"rgb", 300, 200) imageByScalingProportionallyToSize:NSMakeSize(150, 100)] retain];
    }
    result[@"after_pool"] = describe(kept);
    [kept release];

    // Serial and concurrent results agree pixel for pixel.
    NSImage *shared = [source(@"grey", 1024, 768) retain];
    NSData *serial = [[bitmap([shared imageByScalingProportionallyToSize:NSMakeSize(256, 256)]) TIFFRepresentation] retain];
    __block int mismatches = 0, failures = 0;
    dispatch_apply(64, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^(size_t index) {
        @autoreleasepool {
            NSImage *output = [shared imageByScalingProportionallyToSize:NSMakeSize(256, 256)];
            NSData *tiff = [bitmap(output) TIFFRepresentation];
            @synchronized (NSApp ?: (id)[NSNull null]) {
                if (!output) failures++;
                else if (![tiff isEqualToData:serial]) mismatches++;
            }
        }
    });
    result[@"concurrent"] = @{@"calls": @64, @"failures": @(failures), @"mismatches": @(mismatches)};
    [serial release];
    [shared release];
    emit(result);
    return 0;
}

static ScaleIMP loadVariant(const char *path) {
    if (!dlopen(path, RTLD_NOW | RTLD_LOCAL)) { fprintf(stderr, "dlopen %s: %s\n", path, dlerror()); exit(2); }
    return (ScaleIMP)method_getImplementation(class_getInstanceMethod(NSImage.class, @selector(imageByScalingProportionallyToSize:)));
}

static int interleave(const char *dylibA, const char *dylibB, int rounds) {
    ScaleIMP implementations[2] = {loadVariant(dylibA), loadVariant(dylibB)};
    if (implementations[0] == implementations[1]) { fprintf(stderr, "same implementation twice\n"); return 2; }
    const char *first = getenv("HOROS_AB_FIRST");
    int start = (first && strcmp(first, "B") == 0) ? 1 : 0;
    SEL selector = @selector(imageByScalingProportionallyToSize:);
    NSDictionary *scenarios = @{
        @"thumbnail_us": @[source(@"grey", 512, 512), [NSValue valueWithSize:NSMakeSize(128, 128)]],
        @"downscale_large_us": @[source(@"grey", 2048, 2048), [NSValue valueWithSize:NSMakeSize(1024, 1024)]],
        @"same_size_us": @[source(@"grey", 512, 512), [NSValue valueWithSize:NSMakeSize(512, 512)]],
        @"upscale_us": @[source(@"rgb", 256, 256), [NSValue valueWithSize:NSMakeSize(512, 512)]],
        @"letterbox_rgb_us": @[source(@"rgb", 1024, 768), [NSValue valueWithSize:NSMakeSize(768, 768)]],
    };
    NSMutableDictionary *results[2] = {[NSMutableDictionary dictionary], [NSMutableDictionary dictionary]};
    for (int v = 0; v < 2; v++) {
        for (NSString *name in scenarios) results[v][name] = [NSMutableArray array];
        results[v][@"sequence_frame_us"] = [NSMutableArray array];
        results[v][@"concurrent_frame_us"] = [NSMutableArray array];
        results[v][@"invalid_count"] = [NSMutableArray array];
    }
    // Warm both: the first call of each pays set-up that is measured separately.
    for (int v = 0; v < 2; v++)
        for (NSString *name in scenarios) {
            @autoreleasepool { implementations[v](scenarios[name][0], selector, [scenarios[name][1] sizeValue]); }
        }
    NSImage *sequenceSource = [source(@"grey", 512, 512) retain];
    for (int i = 0; i < rounds; i++) {
        for (int slot = 0; slot < 2; slot++) {
            int v = ((i % 2 == 0) == (slot == 0)) ? start : 1 - start;
            int invalid = 0;
            for (NSString *name in scenarios) {
                @autoreleasepool {
                    uint64_t t0 = mach_absolute_time();
                    NSImage *output = implementations[v](scenarios[name][0], selector, [scenarios[name][1] sizeValue]);
                    uint64_t t1 = mach_absolute_time();
                    if (!output) invalid++;
                    [results[v][name] addObject:@(microseconds(t0, t1))];
                }
            }
            // A movie export: frames resized one after another.
            @autoreleasepool {
                uint64_t t0 = mach_absolute_time();
                for (int f = 0; f < 20; f++) {
                    @autoreleasepool { implementations[v](sequenceSource, selector, NSMakeSize(400, 300)); }
                }
                uint64_t t1 = mach_absolute_time();
                [results[v][@"sequence_frame_us"] addObject:@(microseconds(t0, t1) / 20)];
            }
            // The web portal: eight requests at once.
            @autoreleasepool {
                ScaleIMP implementation = implementations[v];
                uint64_t t0 = mach_absolute_time();
                dispatch_apply(8, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^(size_t index) {
                    @autoreleasepool { implementation(sequenceSource, selector, NSMakeSize(256, 256)); }
                });
                uint64_t t1 = mach_absolute_time();
                [results[v][@"concurrent_frame_us"] addObject:@(microseconds(t0, t1) / 8)];
            }
            [results[v][@"invalid_count"] addObject:@(invalid)];
        }
    }
    [sequenceSource release];
    emit(@{@"A": results[0], @"B": results[1]});
    return 0;
}

static double footprintMiB(void) {
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return -1;
    return info.phys_footprint / 1048576.0;
}

static void mallocInUse(double *mib, double *blocks) {
    malloc_statistics_t stats = {0};
    malloc_zone_statistics(NULL, &stats);
    *mib = stats.size_in_use / 1048576.0;
    *blocks = stats.blocks_in_use;
}

// A long movie export in one process: `frames` conversions of a 512 x 512 grey
// frame to 400 x 300, each in its own pool, as the exports do. Footprint and
// malloc use are read after one warm-up conversion (before), every 5 frames
// (the peak), and after the last pool has drained and memory was relieved
// (retained, above before).
static int memoryUse(const char *dylib, int frames) {
    ScaleIMP implementation = loadVariant(dylib);
    SEL selector = @selector(imageByScalingProportionallyToSize:);
    NSImage *input = [source(@"grey", 512, 512) retain];
    @autoreleasepool { implementation(input, selector, NSMakeSize(400, 300)); }
    double before = footprintMiB(), mallocBefore, blocksBefore;
    mallocInUse(&mallocBefore, &blocksBefore);
    double peak = before, mallocPeak = mallocBefore;
    for (int f = 0; f < frames; f++) {
        @autoreleasepool {
            NSImage *output = implementation(input, selector, NSMakeSize(400, 300));
            if (!output) { fprintf(stderr, "no output at frame %d\n", f); return 3; }
        }
        if (f % 5 == 4) {
            double now = footprintMiB(), mallocNow, blocksNow;
            mallocInUse(&mallocNow, &blocksNow);
            if (now > peak) peak = now;
            if (mallocNow > mallocPeak) mallocPeak = mallocNow;
        }
    }
    // Retained is read once deferred purges have had their chance, the same way for
    // both variants: a pressure relief of every malloc zone and half a second. Read
    // straight after the loop, the baseline's footprint differed by tens of MiB from
    // one process to the next with when its caches happened to be trimmed (memory
    // campaign 1 of #625).
    malloc_zone_pressure_relief(NULL, 0);
    usleep(500 * 1000);
    double after = footprintMiB(), mallocAfter, blocksAfter;
    mallocInUse(&mallocAfter, &blocksAfter);
    [input release];
    // In KiB, compared in absolute terms (the _count suffix): a difference of a few
    // hundred KiB is a percentage of nothing when a run retains almost nothing.
    emit(@{@"footprint_peak_kib_count": @[@(lround((peak - before) * 1024))],
           @"footprint_retained_kib_count": @[@(lround((after - before) * 1024))],
           @"malloc_peak_kib_count": @[@(lround((mallocPeak - mallocBefore) * 1024))],
           @"malloc_retained_kib_count": @[@(lround((mallocAfter - mallocBefore) * 1024))],
           @"malloc_blocks_retained_count": @[@(lround(blocksAfter - blocksBefore))]});
    return 0;
}

static int firstConversion(const char *dylib) {
    ScaleIMP implementation = loadVariant(dylib);
    NSImage *input = source(@"grey", 512, 512);
    uint64_t t0 = mach_absolute_time();
    NSImage *output = implementation(input, @selector(imageByScalingProportionallyToSize:), NSMakeSize(256, 256));
    uint64_t t1 = mach_absolute_time();
    emit(@{@"first_us": @[@(microseconds(t0, t1))], @"valid_count": @[@(output != nil)]});
    return 0;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        if (argc >= 2 && strcmp(argv[1], "contract") == 0) return contract();
        if (argc >= 5 && strcmp(argv[1], "interleave") == 0) return interleave(argv[2], argv[3], atoi(argv[4]));
        if (argc >= 3 && strcmp(argv[1], "first") == 0) return firstConversion(argv[2]);
        if (argc >= 4 && strcmp(argv[1], "memory") == 0) return memoryUse(argv[2], atoi(argv[3]));
        fprintf(stderr, "usage: %s contract | interleave <A> <B> <rounds> | first <dylib> | memory <dylib> <frames>\n", argv[0]);
        return 64;
    }
}
