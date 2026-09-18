// Horos's NIfTI and Analyze paths from inside the development app (#631), injected
// with DYLD_INSERT_LIBRARIES and driven by numbered command files.
//
//   HOROS_NIFTI_COMMANDS  a folder: <n>.json is run for n = 1, 2, ... in order, and
//                         answered in <n>.out.json (written whole, then renamed)
//
//   {"action": "ping"}
//   {"action": "import", "paths": [...]}
//       File > Import: -[BrowserController addFilesAndFolderToDatabase:]
//   {"action": "images"}
//       every Image of the database: path, series (name, URI, modality), file type,
//       width, height, frame, number of frames
//   {"action": "open", "series": "<URI>", "points": [[x, y], ...]}
//       the series opened as the browser opens it (-loadSeries::: with the flip
//       the browser asks for), once the viewer has loaded: each frame's size,
//       spacing, thickness, interval, origin, orientation, whether it could be
//       read and why not, the value at each point, and the sum, minimum and
//       maximum of the frame; then the viewer is closed
//   {"action": "xml", "path": "..."}
//       +[DicomFile getNIfTIXML:]: each element's name and value
//   {"action": "detect", "path": "..."}
//       +[DicomFile isNIfTIFile:] and what -[DicomFile init:] makes of the file
//   {"action": "measure", "detect": [paths], "iterations": n,
//    "volumes": [{"label", "path", "frames"}], "xml": path}
//       timed inside the app, for tools/exercise-native-nifti-import.py --memory:
//       detect_us and register_us (+isNIfTIFile: and -[DicomFile init:] per file),
//       <label>_first_us (the first DCMPix of the file in this process),
//       <label>_series_ms and <label>_series_cpu_ms (every frame, one after the other,
//       all kept alive like a viewer's), <label>_peak_kib_count and
//       <label>_retained_kib_count (footprint above the level before the pass, in KiB,
//       at its highest and after the frames are released), <label>_warm_ms (the
//       pass again), xml_us
//
// Also, for every -[DicomDatabase importFilesFromIncomingDir:listenerCompressionSettings:]
// that imported files, a line {"scan_ms", "imported"} in HOROS_NIFTI_SCANS if set.
//
//   xcrun clang -dynamiclib -fobjc-arc -framework Cocoa tools/probe-nifti-import.m -o probe-nifti-import.dylib
#import <Cocoa/Cocoa.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <malloc/malloc.h>
#include <objc/runtime.h>
#include <stdatomic.h>
#include <time.h>

@interface NSObject (NIfTIImportProbe)
+ (id)activeLocalDatabase;
+ (id)currentBrowser;
- (void)addFilesAndFolderToDatabase:(NSArray *)paths;
- (NSArray *)objectsForEntity:(id)entity;
- (id)entityForName:(NSString *)name;
- (id)loadSeries:(id)series :(id)viewer :(BOOL)firstViewer keyImagesOnly:(BOOL)keyImages;
- (BOOL)isEverythingLoaded;
- (NSMutableArray *)pixList;
- (long)pwidth;
- (long)pheight;
- (double)pixelSpacingX;
- (double)pixelSpacingY;
- (double)sliceThickness;
- (double)sliceInterval;
- (double)originX;
- (double)originY;
- (double)originZ;
- (void)orientation:(float *)c;
- (float *)fImage;
- (BOOL)isRGB;
- (BOOL)notAbleToLoadImage;
- (NSString *)missingPixelsReason;
- (long)frameNo;
- (NSString *)srcFile;
+ (BOOL)isNIfTIFile:(NSString *)path;
+ (NSXMLDocument *)getNIfTIXML:(NSString *)path;
- (id)init:(NSString *)path;
- (NSMutableDictionary *)dicomElements;
- (id)initWithPath:(NSString *)s :(long)pos :(long)tot :(float *)ptr :(long)f :(long)ss isBonjour:(BOOL)hello imageObj:(id)iO;
- (void)CheckLoad;
@end

static double milliseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1e6;
}

static unsigned long long footprint(void) {
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return 0;
    return info.phys_footprint;
}

static double threadCPUms(void) {
    struct timespec now;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now);
    return now.tv_sec * 1e3 + now.tv_nsec / 1e6;
}

static id onMain(id (^block)(void)) {
    __block id result = nil;
    if ([NSThread isMainThread]) return block();
    dispatch_sync(dispatch_get_main_queue(), ^{ result = block(); });
    return result;
}

static NSArray *allImages(void) {
    return onMain(^id {
        id database = [NSClassFromString(@"DicomDatabase") activeLocalDatabase];
        return [database objectsForEntity:[database entityForName:@"Image"]] ?: @[];
    });
}

// NSJSONSerialization refuses NaN and infinities; a frame that could not be read
// may hold either.
static id number(double value) {
    return isfinite(value) ? @(value) : [NSNull null];
}

static NSString *uriOf(id object) {
    return [[[object objectID] URIRepresentation] absoluteString] ?: @"";
}

static NSDictionary *images(void) {
    return onMain(^id {
        NSMutableArray *list = [NSMutableArray array];
        for (id image in allImages()) {
            id series = [image valueForKey:@"series"];
            [list addObject:@{@"path": [image valueForKey:@"completePath"] ?: @"",
                              @"series": [series valueForKey:@"name"] ?: @"",
                              @"series_uri": uriOf(series),
                              @"modality": [series valueForKey:@"modality"] ?: @"",
                              @"file_type": [image valueForKey:@"fileType"] ?: @"",
                              @"width": [image valueForKey:@"width"] ?: @0,
                              @"height": [image valueForKey:@"height"] ?: @0,
                              @"frame": [image valueForKey:@"frameID"] ?: @0,
                              @"frames": [image valueForKey:@"numberOfFrames"] ?: @0}];
        }
        return @{@"images": list};
    });
}

static NSDictionary *describePix(id pix, NSArray *points) {
    long width = [pix pwidth], height = [pix pheight];
    float orientation[9] = {0};
    [pix orientation:orientation];
    NSMutableArray *orient = [NSMutableArray array];
    for (int i = 0; i < 9; i++) [orient addObject:number(orientation[i])];
    float *pixels = [pix fImage];
    BOOL rgb = [pix isRGB];
    NSMutableArray *values = [NSMutableArray array];
    for (NSArray *point in points) {
        long x = [point[0] longValue], y = [point[1] longValue];
        if (pixels && !rgb && x < width && y < height) [values addObject:number(pixels[y * width + x])];
        else if (pixels && rgb && x < width && y < height) {
            // A colour frame keeps four bytes a pixel, alpha first: red x 65536 + green x 256 + blue (#643).
            unsigned char *argb = (unsigned char *)pixels + 4 * (y * width + x);
            [values addObject:@(argb[1] * 65536 + argb[2] * 256 + argb[3])];
        }
        else [values addObject:[NSNull null]];
    }
    double sum = 0, minimum = 0, maximum = 0;
    if (pixels && !rgb && width > 0 && height > 0) {
        minimum = maximum = pixels[0];
        for (long i = 0; i < width * height; i++) {
            sum += pixels[i];
            if (pixels[i] < minimum) minimum = pixels[i];
            if (pixels[i] > maximum) maximum = pixels[i];
        }
    }
    return @{@"file": [[pix srcFile] lastPathComponent] ?: @"", @"frame": @([pix frameNo]),
             @"width": @(width), @"height": @(height),
             @"spacing": @[number([pix pixelSpacingX]), number([pix pixelSpacingY])],
             @"thickness": number([pix sliceThickness]), @"interval": number([pix sliceInterval]),
             @"origin": @[number([pix originX]), number([pix originY]), number([pix originZ])], @"orientation": orient,
             @"unreadable": @((BOOL)[pix notAbleToLoadImage]), @"reason": [pix missingPixelsReason] ?: [NSNull null],
             @"rgb": @(rgb), @"values": values, @"sum": number(sum), @"min": number(minimum), @"max": number(maximum)};
}

static NSDictionary *openSeries(NSString *uri, NSArray *points) {
    uint64_t start = mach_absolute_time();
    id viewer = onMain(^id {
        id series = nil;
        for (id image in allImages())
            if ([uriOf([image valueForKey:@"series"]) isEqualToString:uri]) {
                series = [image valueForKey:@"series"];
                break;
            }
        if (!series) return nil;
        return [[NSClassFromString(@"BrowserController") currentBrowser] loadSeries:series :nil :YES keyImagesOnly:NO];
    });
    if (!viewer) return @{@"error": @"no viewer"};
    BOOL loaded = NO;
    for (int wait = 0; wait < 1200 && !loaded; wait++) {
        usleep(50 * 1000);
        loaded = [onMain(^id { return @([viewer isEverythingLoaded]); }) boolValue];
    }
    double openMs = milliseconds(start, mach_absolute_time());
    usleep(200 * 1000);
    return onMain(^id {
        NSMutableArray *frames = [NSMutableArray array];
        for (id pix in [viewer pixList]) [frames addObject:describePix(pix, points)];
        [[viewer window] close];
        return @{@"loaded": @(loaded), @"open_ms": @(openMs), @"frames": frames};
    });
}

static NSDictionary *xml(NSString *path) {
    return onMain(^id {
        NSXMLDocument *document = [NSClassFromString(@"DicomFile") getNIfTIXML:path];
        NSMutableArray *elements = [NSMutableArray array];
        for (NSXMLNode *node in [[document rootElement] children]) {
            NSXMLNode *value = [[(NSXMLElement *)node elementsForName:@"value"] firstObject];
            [elements addObject:@{@"name": [node name] ?: @"", @"value": [value stringValue] ?: @""}];
        }
        return @{@"elements": elements};
    });
}

static NSDictionary *detect(NSString *path) {
    BOOL isNIfTI = [NSClassFromString(@"DicomFile") isNIfTIFile:path];
    id file = [[NSClassFromString(@"DicomFile") alloc] init:path];
    NSDictionary *elements = [file dicomElements];
    return @{@"is_nifti": @(isNIfTI), @"indexed": @(file != nil),
             @"file_type": elements[@"fileType"] ?: [NSNull null], @"modality": elements[@"modality"] ?: [NSNull null],
             @"frames": file ? [file valueForKey:@"NoOfFrames"] : [NSNull null],
             @"width": file ? [file valueForKey:@"width"] : [NSNull null],
             @"height": file ? [file valueForKey:@"height"] : [NSNull null]};
}

static atomic_ullong peakFootprint = 0;
static atomic_bool sampling = false;

static void startSampling(void) {
    atomic_store(&peakFootprint, footprint());
    atomic_store(&sampling, true);
    [NSThread detachNewThreadWithBlock:^{
        while (atomic_load(&sampling)) {
            unsigned long long now = footprint();
            if (now > atomic_load(&peakFootprint)) atomic_store(&peakFootprint, now);
            usleep(2000);
        }
    }];
}

static unsigned long long stopSampling(void) {
    atomic_store(&sampling, false);
    usleep(10 * 1000);
    return atomic_load(&peakFootprint);
}

static void settle(void) {
    uint64_t start = mach_absolute_time();
    volatile unsigned long spin = 0;
    while (milliseconds(start, mach_absolute_time()) < 1.0) spin++;
}

static NSDictionary *measure(NSDictionary *plan) {
    NSMutableDictionary *metrics = [NSMutableDictionary dictionary];
    void (^add)(NSString *, double) = ^(NSString *name, double value) {
        if (!metrics[name]) metrics[name] = [NSMutableArray array];
        [metrics[name] addObject:@(value)];
    };
    Class pixClass = NSClassFromString(@"DCMPix"), fileClass = NSClassFromString(@"DicomFile");

    for (NSDictionary *volume in plan[@"volumes"]) {
        NSString *label = volume[@"label"], *path = volume[@"path"];
        long frames = [volume[@"frames"] longValue];
        @autoreleasepool {
            settle();
            uint64_t t0 = mach_absolute_time();
            id pix = [[pixClass alloc] initWithPath:path :0 :1 :NULL :0 :0 isBonjour:NO imageObj:nil];
            [pix CheckLoad];
            add([label stringByAppendingString:@"_first_us"], milliseconds(t0, mach_absolute_time()) * 1000.0);
            if (![pix fImage] || [pix notAbleToLoadImage]) add(@"failures_count", 1);
            pix = nil;
        }
        for (NSString *pass in @[@"series", @"warm"]) {
            malloc_zone_pressure_relief(NULL, 0);
            usleep(300 * 1000);
            unsigned long long before = footprint();
            NSMutableArray *held = [NSMutableArray array];
            startSampling();
            settle();
            double cpu0 = threadCPUms();
            uint64_t t0 = mach_absolute_time();
            for (long frame = 0; frame < frames; frame++) {
                @autoreleasepool {
                    id pix = [[pixClass alloc] initWithPath:path :frame :frames :NULL :frame :0 isBonjour:NO imageObj:nil];
                    [pix CheckLoad];
                    if (![pix fImage] || [pix notAbleToLoadImage]) add(@"failures_count", 1);
                    [held addObject:pix];
                }
            }
            double elapsed = milliseconds(t0, mach_absolute_time()), cpu = threadCPUms() - cpu0;
            unsigned long long peak = stopSampling();
            add([NSString stringWithFormat:@"%@_%@_ms", label, pass], elapsed);
            if ([pass isEqualToString:@"series"]) {
                add([label stringByAppendingString:@"_series_cpu_ms"], cpu);
                add([label stringByAppendingString:@"_peak_kib_count"], ((double)peak - before) / 1024.0);
            }
            [held removeAllObjects];
            held = nil;
            malloc_zone_pressure_relief(NULL, 0);
            usleep(300 * 1000);
            if ([pass isEqualToString:@"series"])
                add([label stringByAppendingString:@"_retained_kib_count"], ((double)footprint() - before) / 1024.0);
        }
    }

    NSInteger iterations = [plan[@"iterations"] integerValue];
    for (NSInteger iteration = 0; iteration < iterations; iteration++) {
        for (NSString *path in plan[@"detect"]) {
            @autoreleasepool {
                settle();
                uint64_t t0 = mach_absolute_time();
                BOOL isNIfTI = [fileClass isNIfTIFile:path];
                add(@"detect_us", milliseconds(t0, mach_absolute_time()) * 1000.0);
                settle();
                t0 = mach_absolute_time();
                id file = [[fileClass alloc] init:path];
                BOOL indexed = file != nil;
                file = nil;
                add(@"register_us", milliseconds(t0, mach_absolute_time()) * 1000.0);
                if (!isNIfTI || !indexed) add(@"failures_count", 1);
            }
        }
        if (plan[@"xml"]) {
            @autoreleasepool {
                settle();
                uint64_t t0 = mach_absolute_time();
                NSXMLDocument *document = [fileClass getNIfTIXML:plan[@"xml"]];
                add(@"xml_us", milliseconds(t0, mach_absolute_time()) * 1000.0);
                if ([[document rootElement] childCount] == 0) add(@"failures_count", 1);
            }
        }
    }
    if (!metrics[@"failures_count"]) metrics[@"failures_count"] = @[@0];
    else metrics[@"failures_count"] = @[@([metrics[@"failures_count"] count])];
    return metrics;
}

static NSDictionary *run(NSDictionary *command) {
    NSString *action = command[@"action"];
    if ([action isEqualToString:@"ping"]) return @{@"ok": @YES};
    if ([action isEqualToString:@"import"]) {
        onMain(^id {
            [[NSClassFromString(@"BrowserController") currentBrowser] addFilesAndFolderToDatabase:command[@"paths"]];
            return nil;
        });
        return @{@"ok": @YES};
    }
    if ([action isEqualToString:@"images"]) return images();
    if ([action isEqualToString:@"open"]) return openSeries(command[@"series"], command[@"points"] ?: @[]);
    if ([action isEqualToString:@"xml"]) return xml(command[@"path"]);
    if ([action isEqualToString:@"detect"]) return detect(command[@"path"]);
    if ([action isEqualToString:@"measure"]) return measure(command);
    return @{@"error": [NSString stringWithFormat:@"unknown action %@", action]};
}

static const char *scansPath = NULL;
typedef NSInteger (*ImportIMP)(id, SEL, NSNumber *, int);
static ImportIMP originalImport = NULL;

static NSInteger timedImport(id database, SEL selector, NSNumber *showGUI, int compression) {
    uint64_t start = mach_absolute_time();
    NSInteger imported = originalImport(database, selector, showGUI, compression);
    if (imported > 0 && scansPath) {
        FILE *file = fopen(scansPath, "a");
        if (file) {
            fprintf(file, "{\"scan_ms\": %.3f, \"imported\": %ld}\n", milliseconds(start, mach_absolute_time()), (long)imported);
            fclose(file);
        }
    }
    return imported;
}

__attribute__((constructor)) static void installNIfTIImportProbe(void) {
    NSString *folder = NSProcessInfo.processInfo.environment[@"HOROS_NIFTI_COMMANDS"];
    if (!folder) return;
    const char *scans = getenv("HOROS_NIFTI_SCANS");
    if (scans) scansPath = strdup(scans);
    unsetenv("DYLD_INSERT_LIBRARIES");
    unsetenv("HOROS_NIFTI_SCANS");
    Method import = class_getInstanceMethod(objc_getClass("DicomDatabase"),
                                            sel_registerName("importFilesFromIncomingDir:listenerCompressionSettings:"));
    if (import) originalImport = (ImportIMP)method_setImplementation(import, (IMP)timedImport);
    [NSNotificationCenter.defaultCenter addObserverForName:NSApplicationDidFinishLaunchingNotification object:nil
                                                     queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
        [NSThread detachNewThreadWithBlock:^{
            for (NSInteger number = 1;; number++) {
                NSString *commandPath = [folder stringByAppendingPathComponent:[NSString stringWithFormat:@"%ld.json", (long)number]];
                while (![NSFileManager.defaultManager fileExistsAtPath:commandPath]) usleep(50 * 1000);
                @autoreleasepool {
                    NSDictionary *command = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:commandPath]
                                                                            options:0 error:NULL];
                    NSDictionary *answer;
                    @try {
                        answer = command ? run(command) : @{@"error": @"unreadable command"};
                    } @catch (NSException *exception) {
                        answer = @{@"exception": [NSString stringWithFormat:@"%@: %@", exception.name, exception.reason]};
                    }
                    NSData *data = [NSJSONSerialization dataWithJSONObject:answer options:0 error:NULL]
                        ?: [@"{\"error\": \"unserialisable answer\"}" dataUsingEncoding:NSUTF8StringEncoding];
                    NSString *partial = [folder stringByAppendingPathComponent:[NSString stringWithFormat:@".%ld.out.json", (long)number]];
                    [data writeToFile:partial atomically:NO];
                    rename(partial.fileSystemRepresentation,
                           [[folder stringByAppendingPathComponent:[NSString stringWithFormat:@"%ld.out.json", (long)number]] fileSystemRepresentation]);
                }
            }
        }];
    }];
}
