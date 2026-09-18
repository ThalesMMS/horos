// Drives -[NSFileManager moveItemAtPathToTrash:] (#613) from a linked object:
// the application's NSFileManager+N2.o, or the same source at another revision.
//
//   probe trash <path | "<nil>">        BOOL form: {"ok", "resulting", "error"}
//   probe trash-void <path | "<nil>">   void form: {"exists_after"}
//   probe cold <parent>                  first trash call of the process: {"cold_us": [t]}
//   probe interleave <dylib A> <dylib B> <parent> <files> <folders>
//       loads both revisions in this process and alternates the void method
//       call by call (ABBA pairs, HOROS_AB_FIRST first) on uniquely named
//       synthetic files and folders; each trashed item is found at the name
//       both revisions give a first item, moved back and deleted - nothing
//       else in the Trash is looked at. Prints {"A": {...}, "B": {...}}.
//
// Built without ARC, like the object it links.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <mach/mach_time.h>
#include <objc/runtime.h>

@interface NSFileManager (N2TrashProbe)
- (void)moveItemAtPathToTrash:(NSString *)path;
- (BOOL)moveItemAtPathToTrash:(NSString *)path resultingPath:(NSString **)resultingPath error:(NSError **)error;
@end

@interface HorosStorageFailure : NSObject
+ (NSString *)reasonForError:(NSError *)error path:(NSString *)path;
@end
@implementation HorosStorageFailure
+ (NSString *)reasonForError:(NSError *)error path:(NSString *)path { return path; }
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

static NSString *argumentPath(const char *text) {
    NSString *path = @(text);
    return [path isEqualToString:@"<nil>"] ? nil : path;
}

typedef void (*TrashIMP)(id, SEL, NSString *);

static TrashIMP loadVariant(const char *path) {
    if (!dlopen(path, RTLD_NOW | RTLD_LOCAL)) {
        fprintf(stderr, "dlopen %s: %s\n", path, dlerror());
        exit(2);
    }
    return (TrashIMP)method_getImplementation(class_getInstanceMethod(NSFileManager.class, @selector(moveItemAtPathToTrash:)));
}

static int interleave(const char *dylibA, const char *dylibB, NSString *parent, int files, int folders) {
    TrashIMP implementations[2] = {loadVariant(dylibA), loadVariant(dylibB)};
    if (implementations[0] == implementations[1]) { fprintf(stderr, "same implementation twice\n"); return 2; }
    const char *first = getenv("HOROS_AB_FIRST");
    int start = (first && strcmp(first, "B") == 0) ? 1 : 0;
    NSFileManager *fm = NSFileManager.defaultManager;
    NSString *trash = [@"~/.Trash" stringByExpandingTildeInPath];
    NSString *run = [NSUUID UUID].UUIDString;
    NSString *root = [parent stringByAppendingPathComponent:[@"trash-interleave-" stringByAppendingString:run]];
    [fm createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:NULL];
    NSData *payload = [NSMutableData dataWithLength:4096];
    NSMutableArray *times[2][2] = {{[NSMutableArray array], [NSMutableArray array]}, {[NSMutableArray array], [NSMutableArray array]}};
    int status = 0;
    for (int kind = 0; kind < 2 && status == 0; kind++) {
        int count = kind == 0 ? files : folders;
        for (int i = 0; i < count && status == 0; i++) {
            for (int slot = 0; slot < 2 && status == 0; slot++) {
                int v = ((i % 2 == 0) == (slot == 0)) ? start : 1 - start;
                @autoreleasepool {
                    NSString *name = [NSString stringWithFormat:@"horos-trash-bench-%@-%d-%d-%d%@", run, kind, i, v, kind == 0 ? @".dcm" : @""];
                    NSString *item = [root stringByAppendingPathComponent:name];
                    if (kind == 0) {
                        [payload writeToFile:item atomically:NO];
                    } else {
                        [fm createDirectoryAtPath:item withIntermediateDirectories:NO attributes:nil error:NULL];
                        for (int f = 0; f < 20; f++)
                            [payload writeToFile:[item stringByAppendingPathComponent:[NSString stringWithFormat:@"%d.dcm", f]] atomically:NO];
                    }
                    uint64_t t0 = mach_absolute_time();
                    implementations[v](fm, @selector(moveItemAtPathToTrash:), item);
                    uint64_t t1 = mach_absolute_time();
                    NSString *trashed = [trash stringByAppendingPathComponent:name];
                    if ([fm fileExistsAtPath:item] || ![fm moveItemAtPath:trashed toPath:item error:NULL]) {
                        fprintf(stderr, "variant %d did not trash %s where expected\n", v, name.UTF8String);
                        status = 3;
                    }
                    [fm removeItemAtPath:item error:NULL];
                    [times[v][kind] addObject:@(microseconds(t0, t1))];
                }
            }
        }
    }
    [fm removeItemAtPath:root error:NULL];
    if (status) return status;
    emit(@{@"A": @{@"file_us": times[0][0], @"folder_us": times[0][1]},
           @"B": @{@"file_us": times[1][0], @"folder_us": times[1][1]}});
    return 0;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        NSFileManager *fm = NSFileManager.defaultManager;
        if (argc >= 3 && strcmp(argv[1], "trash") == 0) {
            NSString *resulting = nil;
            NSError *error = nil;
            BOOL ok = [fm moveItemAtPathToTrash:argumentPath(argv[2]) resultingPath:&resulting error:&error];
            emit(@{@"ok": @(ok), @"resulting": resulting ?: [NSNull null],
                   @"error": error ? @{@"domain": error.domain, @"code": @(error.code),
                                       @"description": error.localizedDescription ?: @""} : [NSNull null]});
            return 0;
        }
        if (argc >= 3 && strcmp(argv[1], "trash-void") == 0) {
            NSString *path = argumentPath(argv[2]);
            [fm moveItemAtPathToTrash:path];
            emit(@{@"exists_after": @(path.length ? [fm fileExistsAtPath:path] : NO)});
            return 0;
        }
        if (argc >= 3 && strcmp(argv[1], "cold") == 0) {
            // The first trash call of a process: framework and service set-up
            // included, which is what a quit or an export pays once.
            NSString *root = [@(argv[2]) stringByAppendingPathComponent:[@"trash-cold-" stringByAppendingString:NSUUID.UUID.UUIDString]];
            [fm createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:NULL];
            NSString *name = [NSString stringWithFormat:@"horos-trash-cold-%@.dcm", NSUUID.UUID.UUIDString];
            NSString *item = [root stringByAppendingPathComponent:name];
            [[NSMutableData dataWithLength:4096] writeToFile:item atomically:NO];
            uint64_t t0 = mach_absolute_time();
            [fm moveItemAtPathToTrash:item];
            uint64_t t1 = mach_absolute_time();
            NSString *trashed = [[@"~/.Trash" stringByExpandingTildeInPath] stringByAppendingPathComponent:name];
            BOOL restored = ![fm fileExistsAtPath:item] && [fm moveItemAtPath:trashed toPath:item error:NULL];
            [fm removeItemAtPath:root error:NULL];
            if (!restored) { fprintf(stderr, "the item did not reach %s\n", trashed.UTF8String); return 3; }
            emit(@{@"cold_us": @[@(microseconds(t0, t1))]});
            return 0;
        }
        if (argc >= 7 && strcmp(argv[1], "interleave") == 0)
            return interleave(argv[2], argv[3], @(argv[4]), atoi(argv[5]), atoi(argv[6]));
        fprintf(stderr, "usage: %s trash|trash-void <path> | interleave <A> <B> <parent> <files> <folders>\n", argv[0]);
        return 64;
    }
}
