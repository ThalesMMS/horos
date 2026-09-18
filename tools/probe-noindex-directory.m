// Drives -[NSFileManager confirmNoIndexDirectoryAtPath:] from a linked object
// file: the application's own NSFileManager+N2.o for tests (#612), or the same
// source recompiled at another revision for the A/B measurement.
//
//   probe confirm <path | "<nil>">
//       one call; prints {"result": path|null} or {"exception", "reason"}
//   probe bench <parent folder> <hot calls> <create calls> <legacy suffix>
//       works in a new mkdtemp folder under <parent>, removed afterwards (not
//       timed), and prints per-call latencies in microseconds for three file
//       operations:
//       an existing directory (what every imported file asks for), a new one,
//       and a legacy directory migrated to the .noindex name. The legacy name
//       is the request plus <legacy suffix>, so each revision migrates what it
//       recognises as legacy ("" for the fixed helper, ".noindex" before it).
//   probe interleave <dylib A> <dylib B> <parent> <hot> <create> <suffix A> <suffix B>
//       loads each revision's NSFileManager+N2 as a dylib in this process,
//       keeps each one's implementation of the method, and alternates the two
//       call by call (ABBA pairs; HOROS_AB_FIRST says which starts) on the same
//       three operations. Prints {"A": {...}, "B": {...}}. The method's own
//       call to -confirmDirectoryAtPath: goes to the last image loaded; that
//       method is identical in both revisions of #612.
//
// Built without ARC, like the object it links.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <mach/mach_time.h>
#include <objc/runtime.h>

@interface NSFileManager (N2NoIndexProbe)
-(NSString*)confirmNoIndexDirectoryAtPath:(NSString*)path;
@end

// Project classes NSFileManager+N2.o names; neither is reached by this method
// except HorosStorageFailure, and only when a directory cannot be created.
@interface HorosStorageFailure : NSObject
+(NSString*)reasonForError:(NSError*)error path:(NSString*)path;
@end
@implementation HorosStorageFailure
+(NSString*)reasonForError:(NSError*)error path:(NSString*)path {
    return [NSString stringWithFormat:@"cannot create %@: %@", path, error.localizedDescription];
}
@end
@interface N2DirectoryEnumerator : NSObject @end
@implementation N2DirectoryEnumerator @end

static void emit(NSDictionary *object) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:NULL];
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
}

static double microseconds(uint64_t start, uint64_t end) {
    static mach_timebase_info_data_t timebase;
    if (timebase.denom == 0) mach_timebase_info(&timebase);
    return (double)(end - start) * timebase.numer / timebase.denom / 1000.0;
}

static int confirm(NSString *path) {
    @try {
        NSString *result = [NSFileManager.defaultManager confirmNoIndexDirectoryAtPath:path];
        emit(@{@"result": result ?: [NSNull null]});
    } @catch (NSException *e) {
        emit(@{@"exception": e.name ?: @"", @"reason": e.reason ?: @""});
    }
    return 0;
}

static int bench(NSString *parent, int hot, int create, NSString *legacySuffix) {
    NSFileManager *fm = NSFileManager.defaultManager;
    char *pattern = strdup([parent stringByAppendingPathComponent:@"noindex-bench-XXXXXX"].fileSystemRepresentation);
    if (!mkdtemp(pattern)) { perror("mkdtemp"); return 2; }
    NSString *root = [fm stringWithFileSystemRepresentation:pattern length:strlen(pattern)];
    free(pattern);
    int status = 0;
    NSMutableArray *hotTimes = [NSMutableArray array], *createTimes = [NSMutableArray array],
                   *migrateTimes = [NSMutableArray array];
    NSString *existing = [root stringByAppendingPathComponent:@"Horos Data/DATABASE.noindex"];
    [fm confirmNoIndexDirectoryAtPath:existing];
    for (int i = 0; i < hot; i++) {
        @autoreleasepool {
            uint64_t start = mach_absolute_time();
            [fm confirmNoIndexDirectoryAtPath:existing];
            uint64_t end = mach_absolute_time();
            [hotTimes addObject:@(microseconds(start, end))];
        }
    }
    NSString *fresh = [root stringByAppendingPathComponent:@"Horos Data/new"];
    for (int i = 0; i < create; i++) {
        @autoreleasepool {
            NSString *path = [fresh stringByAppendingPathComponent:[NSString stringWithFormat:@"INCOMING-%d.noindex", i]];
            uint64_t start = mach_absolute_time();
            [fm confirmNoIndexDirectoryAtPath:path];
            uint64_t end = mach_absolute_time();
            [createTimes addObject:@(microseconds(start, end))];
        }
    }
    NSString *legacyRoot = [root stringByAppendingPathComponent:@"Horos Data/legacy"];
    for (int i = 0; i < create; i++) {
        @autoreleasepool {
            NSString *path = [legacyRoot stringByAppendingPathComponent:[NSString stringWithFormat:@"TEMP-%d.noindex", i]];
            NSString *legacy = [path stringByAppendingString:legacySuffix];
            if (legacySuffix.length == 0)
                legacy = [path substringToIndex:path.length - @".noindex".length];
            [fm createDirectoryAtPath:[legacy stringByAppendingPathComponent:@"content"] withIntermediateDirectories:YES attributes:nil error:NULL];
            uint64_t start = mach_absolute_time();
            [fm confirmNoIndexDirectoryAtPath:path];
            uint64_t end = mach_absolute_time();
            BOOL isDirectory = NO;
            if (![fm fileExistsAtPath:[path stringByAppendingPathComponent:@"content"] isDirectory:&isDirectory] || !isDirectory) {
                fprintf(stderr, "migration did not happen for %s\n", path.fileSystemRepresentation);
                status = 3;
                break;
            }
            [migrateTimes addObject:@(microseconds(start, end))];
        }
    }
    [fm removeItemAtPath:root error:NULL];
    if (status == 0)
        emit(@{@"existing_us": hotTimes, @"create_us": createTimes, @"migrate_us": migrateTimes});
    return status;
}

typedef NSString *(*ConfirmIMP)(id, SEL, NSString *);

static ConfirmIMP loadVariant(const char *path) {
    if (!dlopen(path, RTLD_NOW | RTLD_LOCAL)) {
        fprintf(stderr, "dlopen %s: %s\n", path, dlerror());
        exit(2);
    }
    Method method = class_getInstanceMethod(NSFileManager.class, @selector(confirmNoIndexDirectoryAtPath:));
    return (ConfirmIMP)method_getImplementation(method);
}

static int interleave(const char *dylibA, const char *dylibB, NSString *parent, int hot, int create,
                      NSString *suffixA, NSString *suffixB) {
    ConfirmIMP implementations[2] = {loadVariant(dylibA), loadVariant(dylibB)};
    if (implementations[0] == implementations[1]) {
        fprintf(stderr, "both variants resolved to the same implementation\n");
        return 2;
    }
    NSString *suffixes[2] = {suffixA, suffixB};
    const char *first = getenv("HOROS_AB_FIRST");
    int start = (first && strcmp(first, "B") == 0) ? 1 : 0;
    NSFileManager *fm = NSFileManager.defaultManager;
    SEL selector = @selector(confirmNoIndexDirectoryAtPath:);
    char *pattern = strdup([parent stringByAppendingPathComponent:@"noindex-interleave-XXXXXX"].fileSystemRepresentation);
    if (!mkdtemp(pattern)) { perror("mkdtemp"); return 2; }
    NSString *root = [fm stringWithFileSystemRepresentation:pattern length:strlen(pattern)];
    free(pattern);
    NSMutableArray *times[2][3];
    for (int v = 0; v < 2; v++)
        for (int k = 0; k < 3; k++)
            times[v][k] = [NSMutableArray array];
    // Pair i runs (start, other) when i is even and (other, start) when odd: ABBA.
    #define VARIANT_AT(i, slot) ((((i) % 2 == 0) == ((slot) == 0)) ? start : 1 - start)
    NSString *existing[2];
    for (int v = 0; v < 2; v++) {
        existing[v] = [root stringByAppendingPathComponent:[NSString stringWithFormat:@"Horos Data %d/DATABASE.noindex", v]];
        implementations[v](fm, selector, existing[v]);
    }
    for (int i = 0; i < hot; i++) {
        for (int slot = 0; slot < 2; slot++) {
            int v = VARIANT_AT(i, slot);
            @autoreleasepool {
                uint64_t t0 = mach_absolute_time();
                implementations[v](fm, selector, existing[v]);
                uint64_t t1 = mach_absolute_time();
                [times[v][0] addObject:@(microseconds(t0, t1))];
            }
        }
    }
    for (int i = 0; i < create; i++) {
        for (int slot = 0; slot < 2; slot++) {
            int v = VARIANT_AT(i, slot);
            @autoreleasepool {
                NSString *path = [root stringByAppendingPathComponent:[NSString stringWithFormat:@"new/INCOMING-%d-%d.noindex", v, i]];
                uint64_t t0 = mach_absolute_time();
                implementations[v](fm, selector, path);
                uint64_t t1 = mach_absolute_time();
                [times[v][1] addObject:@(microseconds(t0, t1))];
            }
        }
    }
    for (int i = 0; i < create; i++) {
        for (int slot = 0; slot < 2; slot++) {
            int v = VARIANT_AT(i, slot);
            @autoreleasepool {
                NSString *path = [root stringByAppendingPathComponent:[NSString stringWithFormat:@"legacy/TEMP-%d-%d.noindex", v, i]];
                NSString *legacy = suffixes[v].length ? [path stringByAppendingString:suffixes[v]]
                                                      : [path substringToIndex:path.length - @".noindex".length];
                [fm createDirectoryAtPath:[legacy stringByAppendingPathComponent:@"content"] withIntermediateDirectories:YES attributes:nil error:NULL];
                uint64_t t0 = mach_absolute_time();
                implementations[v](fm, selector, path);
                uint64_t t1 = mach_absolute_time();
                BOOL isDirectory = NO;
                if (![fm fileExistsAtPath:[path stringByAppendingPathComponent:@"content"] isDirectory:&isDirectory] || !isDirectory) {
                    fprintf(stderr, "variant %d did not migrate %s\n", v, path.fileSystemRepresentation);
                    [fm removeItemAtPath:root error:NULL];
                    return 3;
                }
                [times[v][2] addObject:@(microseconds(t0, t1))];
            }
        }
    }
    [fm removeItemAtPath:root error:NULL];
    NSMutableDictionary *output = [NSMutableDictionary dictionary];
    const char *names[2] = {"A", "B"};
    for (int v = 0; v < 2; v++)
        output[@(names[v])] = @{@"existing_us": times[v][0], @"create_us": times[v][1], @"migrate_us": times[v][2]};
    emit(output);
    return 0;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc >= 3 && strcmp(argv[1], "confirm") == 0) {
            NSString *path = @(argv[2]);
            return confirm([path isEqualToString:@"<nil>"] ? nil : path);
        }
        if (argc >= 9 && strcmp(argv[1], "interleave") == 0)
            return interleave(argv[2], argv[3], @(argv[4]), atoi(argv[5]), atoi(argv[6]), @(argv[7]), @(argv[8]));
        if (argc >= 6 && strcmp(argv[1], "bench") == 0)
            return bench(@(argv[2]), atoi(argv[3]), atoi(argv[4]), @(argv[5]));
        fprintf(stderr, "usage: %s confirm <path|<nil>> | bench <root> <hot> <create> <legacy suffix>\n", argv[0]);
        return 64;
    }
}
