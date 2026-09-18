// The Protocols preference pane's copy of HANGINGPROTOCOLS, exercised on the app's
// own compiled object (#618). The pane is linked in (OSIHangingPreferencePanePref.o)
// or loaded from a dylib given as the last argument - the pane compiled at a revision
// together with that revision's Nitrogen collection categories, as
// tools/measure-object-interleaved.py builds it. The classes the pane reaches beyond
// willSelect/willUnselect are stubbed here.
//
// NSUserDefaults is replaced by an in-memory subclass: nothing is read from or
// written to any preferences domain on disk.
//
//   probe-hanging-protocols check [pane.dylib]
//       JSON: isolation of the edited copy from the stored value, mutability of every
//       nested container, the value written back, type preservation, a stored value
//       that is not a dictionary (a string, an array), no value at all, and memory
//       retained over 500 visits to the pane
//   probe-hanging-protocols time <visits> [pane.dylib]
//       JSON: {"select_small_us": [...], "unselect_small_us": [...], "select_large_us": [...],
//       "unselect_large_us": [...]}, one per visit, alternating the registered protocols'
//       size (13 modalities, one protocol each) and a large set (13 x 40); the stored
//       value is immutable at every level, as NSUserDefaults returns it. Each size has
//       its own pane: a visit frees the copy the previous visit of that size made, as a
//       return to the pane does in the app (one pane for both charged the release of
//       the large copy to the small visit)
//
//   xcrun clang -fno-objc-arc -framework Cocoa -framework PreferencePanes tools/probe-hanging-protocols.m \
//       [OSIHangingPreferencePanePref.o] -Wl,-undefined,dynamic_lookup -Wl,-export_dynamic -o probe
#import <Cocoa/Cocoa.h>
#import <PreferencePanes/PreferencePanes.h>
#include <dlfcn.h>
#include <malloc/malloc.h>
#include <mach/mach_time.h>
#include <objc/runtime.h>

// --- stubs for what the pane's other methods reach ------------------------------------------
@interface WindowLayoutManager : NSObject
@end
@implementation WindowLayoutManager
+ (int)windowsRowsForHangingProtocol:(NSDictionary *)protocol { return 1; }
+ (int)windowsColumnsForHangingProtocol:(NSDictionary *)protocol { return 2; }
+ (int)imagesRowsForHangingProtocol:(NSDictionary *)protocol { return 3; }
+ (int)imagesColumnsForHangingProtocol:(NSDictionary *)protocol { return 4; }
@end

@interface AppController : NSObject
@end
@implementation AppController
+ (id)sharedAppController { return nil; }
@end

// --- preferences in memory -----------------------------------------------------------------
@interface ProbeDefaults : NSUserDefaults
@property (retain) NSMutableDictionary *stored;
@property (retain) NSMutableDictionary *registered;
@property NSInteger writes;
@end

@implementation ProbeDefaults
- (instancetype)init {
    if ((self = [super initWithSuiteName:@"org.horosproject.horos.local-development.probe618-unused"])) {
        _stored = [NSMutableDictionary new];
        _registered = [NSMutableDictionary new];
    }
    return self;
}
- (id)objectForKey:(NSString *)key { return _stored[key] ?: _registered[key]; }
- (void)setObject:(id)value forKey:(NSString *)key {
    _writes++;
    if (value) _stored[key] = value; else [_stored removeObjectForKey:key];
}
- (void)removeObjectForKey:(NSString *)key { [_stored removeObjectForKey:key]; }
- (NSDictionary *)dictionaryForKey:(NSString *)key {
    id value = [self objectForKey:key];
    return [value isKindOfClass:[NSDictionary class]] ? value : nil;
}
- (NSDictionary *)volatileDomainForName:(NSString *)name {
    return [name isEqualToString:NSRegistrationDomain] ? _registered : @{};
}
- (BOOL)synchronize { return YES; }
@end

static ProbeDefaults *defaults;
static id standardDefaults(id self, SEL _cmd) { return defaults; }

// --- helpers -------------------------------------------------------------------------------
static NSData *plist(id object) {
    return object ? [NSPropertyListSerialization dataWithPropertyList:object format:NSPropertyListBinaryFormat_v1_0 options:0 error:NULL] : nil;
}

static NSMutableDictionary *protocols(NSUInteger modalities, NSUInteger perModality) {
    NSMutableDictionary *all = [NSMutableDictionary dictionary];
    for (NSUInteger m = 0; m < modalities; m++) {
        NSMutableArray *list = [NSMutableArray array];
        for (NSUInteger p = 0; p < perModality; p++) {
            [list addObject:[@{@"Study Description": [NSString stringWithFormat:@"Protocol %lu", (unsigned long)p],
                               @"WindowsTiling": @(p % 4), @"ImageTiling": @(p % 3), @"WL": @(p % 2 ? 40 : 0),
                               @"WW": @(p % 2 ? 400 : 0), @"Sync": @YES, @"Propagate": @NO,
                               @"NumberOfSeriesPerComparative": @2, @"Comparative": @(0.5),
                               @"Created": [NSDate dateWithTimeIntervalSince1970:1789600000],
                               @"Blob": [@"horos" dataUsingEncoding:NSUTF8StringEncoding]} mutableCopy]];
        }
        all[m == 0 ? @"CR" : [NSString stringWithFormat:@"M%02lu", (unsigned long)m]] = list;
    }
    return all;
}

// What NSUserDefaults hands back: a property list immutable at every level.
static id storedForm(id value) {
    return [NSPropertyListSerialization propertyListWithData:plist(value) options:NSPropertyListImmutable format:NULL error:NULL];
}

static BOOL mutableThroughout(id value, NSMutableArray *where, NSString *path) {
    if ([value isKindOfClass:[NSDictionary class]]) {
        BOOL ok = [value isKindOfClass:[NSMutableDictionary class]];
        if (ok) {
            @try { [value setObject:@1 forKey:@"__probe"]; [value removeObjectForKey:@"__probe"]; }
            @catch (NSException *e) { ok = NO; }
        }
        if (!ok) [where addObject:path];
        for (id key in [value allKeys]) ok &= mutableThroughout(value[key], where, [path stringByAppendingFormat:@".%@", key]);
        return ok;
    }
    if ([value isKindOfClass:[NSArray class]]) {
        BOOL ok = [value isKindOfClass:[NSMutableArray class]];
        if (ok) {
            @try { [value addObject:@1]; [value removeLastObject]; }
            @catch (NSException *e) { ok = NO; }
        }
        if (!ok) [where addObject:path];
        NSUInteger index = 0;
        for (id item in [[value copy] autorelease]) ok &= mutableThroughout(item, where, [path stringByAppendingFormat:@"[%lu]", (unsigned long)index++]);
        return ok;
    }
    return YES;
}

// Without -initWithBundle:, which loads the pane's nib and builds its menus from
// the running application: willSelect, willUnselect and dealloc use only the pane's
// own variables, all nil in a new instance.
static id newPane(void) {
    return class_createInstance(objc_getClass("OSIHangingPreferencePanePref"), 0);
}

static NSMutableDictionary *edited(id pane) {
    Ivar ivar = class_getInstanceVariable([pane class], "hangingProtocols");
    return ivar ? object_getIvar(pane, ivar) : nil;
}

static NSDictionary *visit(NSString *label, id stored, id registered, void (^edit)(NSMutableDictionary *)) {
    [defaults.stored removeAllObjects];
    [defaults.registered removeAllObjects];
    if (stored) defaults.stored[@"HANGINGPROTOCOLS"] = stored;
    if (registered) defaults.registered[@"HANGINGPROTOCOLS"] = registered;
    NSData *storedBefore = plist(stored);
    NSMutableDictionary *result = [NSMutableDictionary dictionaryWithObject:label forKey:@"case"];
    id pane = newPane();
    @try {
        [pane willSelect];
        NSMutableDictionary *copy = edited(pane);
        result[@"copy_class"] = copy ? NSStringFromClass([copy class]) : [NSNull null];
        result[@"copy_is_stored_object"] = @(copy != nil && copy == stored);
        NSMutableArray *immutable = [NSMutableArray array];
        result[@"mutable_throughout"] = @(copy ? mutableThroughout(copy, immutable, @"") : NO);
        result[@"immutable_paths"] = immutable;
        if (edit && copy) edit(copy);
        // What the pane edits must not show through in the stored value before it is saved.
        result[@"stored_untouched_before_save"] = @(storedBefore == nil ? YES : [plist(defaults.stored[@"HANGINGPROTOCOLS"]) isEqual:storedBefore]);
        NSInteger writes = defaults.writes;
        [pane willUnselect];
        result[@"wrote"] = @(defaults.writes > writes);
        id after = defaults.stored[@"HANGINGPROTOCOLS"];
        result[@"stored_after_class"] = after ? NSStringFromClass([after class]) : [NSNull null];
        result[@"stored_after_equals_before"] = @(storedBefore != nil && [plist(after) isEqual:storedBefore]);
        result[@"stored_after_equals_copy"] = @(copy != nil && after != nil && [plist(after) isEqual:plist(copy)]);
        if ([after isKindOfClass:[NSDictionary class]]) {
            NSDictionary *first = [after[@"CR"] firstObject];
            result[@"first_protocol_types"] = @{@"Created": NSStringFromClass([first[@"Created"] class] ?: [NSNull class]),
                                                @"Blob": NSStringFromClass([first[@"Blob"] class] ?: [NSNull class]),
                                                @"Comparative": [first[@"Comparative"] description] ?: @"",
                                                @"Rows": [first[@"Rows"] description] ?: @""};
        }
    } @catch (NSException *exception) {
        result[@"exception"] = [NSString stringWithFormat:@"%@: %@", exception.name, exception.reason];
        result[@"stored_after_equals_before"] = @(storedBefore != nil && [plist(defaults.stored[@"HANGINGPROTOCOLS"]) isEqual:storedBefore]);
    }
    [pane release];
    return result;
}

static size_t inUse(void) {
    malloc_statistics_t statistics;
    malloc_zone_statistics(NULL, &statistics);
    return statistics.size_in_use;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        defaults = [ProbeDefaults new];
        method_setImplementation(class_getClassMethod([NSUserDefaults class], @selector(standardUserDefaults)), (IMP)standardDefaults);
        const char *last = argv[argc - 1];
        size_t length = strlen(last);
        if (length > 6 && strcmp(last + length - 6, ".dylib") == 0 && !dlopen(last, RTLD_NOW | RTLD_LOCAL)) {
            fprintf(stderr, "dlopen %s: %s\n", last, dlerror());
            return 2;
        }
        if (!objc_getClass("OSIHangingPreferencePanePref")) {
            fprintf(stderr, "the pane's object is not linked\n");
            return 2;
        }
        if (argc >= 2 && strcmp(argv[1], "check") == 0) {
            NSMutableArray *cases = [NSMutableArray array];
            NSMutableDictionary *saved = protocols(3, 4);
            NSMutableDictionary *registered = protocols(2, 2);
            [cases addObject:visit(@"stored", saved, registered, ^(NSMutableDictionary *copy) {
                [copy[@"CR"] addObject:[@{@"Study Description": @"added in the pane", @"WLWW": @100} mutableCopy]];
                [copy[@"CR"][0] setObject:@"renamed in the pane" forKey:@"Study Description"];
            })];
            [cases addObject:visit(@"registered only", nil, registered, nil)];
            [cases addObject:visit(@"stored string", @"not protocols", registered, nil)];
            [cases addObject:visit(@"stored array", @[@"not", @"protocols"], registered, nil)];
            [cases addObject:visit(@"nothing", nil, nil, nil)];

            // Visits: the pane object lives as long as the application and each return
            // to it calls willSelect again.
            [defaults.stored removeAllObjects];
            defaults.stored[@"HANGINGPROTOCOLS"] = protocols(10, 40);
            id pane = newPane();
            for (int warm = 0; warm < 20; warm++) @autoreleasepool { [pane willSelect]; [pane willUnselect]; }
            malloc_zone_pressure_relief(NULL, 0);
            size_t before = inUse();
            for (int visit = 0; visit < 500; visit++) @autoreleasepool { [pane willSelect]; [pane willUnselect]; }
            malloc_zone_pressure_relief(NULL, 0);
            size_t after = inUse();
            [pane release];
            NSDictionary *output = @{@"cases": cases, @"visits": @500,
                                     @"retained_bytes_per_visit": @(((double)after - (double)before) / 500.0)};
            NSData *json = [NSJSONSerialization dataWithJSONObject:output options:0 error:NULL];
            fwrite(json.bytes, 1, json.length, stdout);
            printf("\n");
            return 0;
        }
        if (argc >= 3 && strcmp(argv[1], "time") == 0) {
            int visits = atoi(argv[2]);
            NSDictionary *sets[2] = {[storedForm(protocols(13, 1)) retain], [storedForm(protocols(13, 40)) retain]};
            NSString *names[2] = {@"small", @"large"};
            NSMutableDictionary *series = [NSMutableDictionary dictionary];
            for (int s = 0; s < 2; s++)
                for (NSString *step in @[@"select", @"unselect"])
                    series[[NSString stringWithFormat:@"%@_%@_us", step, names[s]]] = [NSMutableArray array];
            id panes[2] = {newPane(), newPane()};
            mach_timebase_info_data_t timebase;
            mach_timebase_info(&timebase);
            // Alternate the sizes visit by visit; the value the pane saves on leaving is
            // replaced by the stored form again, so every visit copies the same input.
            for (int visit = 0; visit < 2 * visits; visit++) @autoreleasepool {
                int s = visit % 2;
                defaults.stored[@"HANGINGPROTOCOLS"] = sets[s];
                uint64_t t0 = mach_absolute_time();
                [panes[s] willSelect];
                uint64_t t1 = mach_absolute_time();
                [panes[s] willUnselect];
                uint64_t t2 = mach_absolute_time();
                [series[[NSString stringWithFormat:@"select_%@_us", names[s]]] addObject:@((double)(t1 - t0) * timebase.numer / timebase.denom / 1000.0)];
                [series[[NSString stringWithFormat:@"unselect_%@_us", names[s]]] addObject:@((double)(t2 - t1) * timebase.numer / timebase.denom / 1000.0)];
            }
            [panes[0] release];
            [panes[1] release];
            NSData *json = [NSJSONSerialization dataWithJSONObject:series options:0 error:NULL];
            fwrite(json.bytes, 1, json.length, stdout);
            printf("\n");
            return 0;
        }
        fprintf(stderr, "usage: %s check [pane.dylib] | time <visits> [pane.dylib]\n", argv[0]);
        return 2;
    }
}
