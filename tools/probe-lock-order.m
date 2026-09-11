// Diagnostic-only probe: record who holds Horos's locks, who waits for them, and
// in what order they are taken.
//
//   clang -shared -fobjc-arc -framework Foundation tools/probe-lock-order.m \
//     -o <dir>/lock-probe.dylib && codesign --force --sign - <dir>/lock-probe.dylib
//
// Injected with DYLD_INSERT_LIBRARIES into the development bundle, which needs
// `com.apple.security.cs.allow-dyld-environment-variables`; `script/build_and_run.sh
// --diagnostics` builds and signs it that way. `nohup` is a platform binary and
// dyld purges DYLD_* for those, so launch from a subshell with `exec` instead.
//
//   HOROS_LOCK_MS       a wait or a hold longer than this is reported (default 250)
//   HOROS_LOCK_REPORT   seconds between standing reports (default 20; 0 for none)
//
// Every -[NSLock lock], -[NSRecursiveLock lock] and -[NSConditionLock lock…] is
// passed straight through, with the time around it recorded. What comes out:
//
//   LOCK116 waited     somebody was kept waiting longer than the threshold
//   LOCK116 held       a lock was held longer than the threshold, by which thread
//   LOCK116 order      two locks were taken in one order here and the other order
//                      somewhere else - the shape a deadlock needs
//   LOCK116 standing   what is held right now, printed from a thread of its own so
//                      it still appears while the main thread is inside a wait loop
//   LOCK116 ledger     per lock: how often taken, how long held, how long waited for
//
// Horos makes one lock per DCMPix, so addresses are useless as names and there
// are thousands of them. A lock is identified instead by its class and the
// innermost application frames of its first acquisition, and the ledger is
// totalled over that identity: every per-image lock born in -[DCMPix CheckLoad]
// is one row. The locks Horos exports as globals - PapyrusLock and the two
// store-SCP locks - are named by symbol.
//
// The lock object itself is never messaged after that first sight and never
// retained: a per-image lock is deallocated while its row lives on, and asking a
// freed object for its class from the reporting thread would crash the very
// application being measured.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <os/lock.h>
#import <pthread.h>
#import <mach/mach_time.h>
#import <dlfcn.h>
#import <execinfo.h>

#define MAX_HELD 64

typedef struct {
    CFStringRef identity;        // owned here, never released
    char owner[64];              // the holding thread's name, copied when taken
    uint64_t since;              // when the outermost acquisition happened
    unsigned depth;
    unsigned long acquisitions;
    double heldMilliseconds, longestHold;
    double waitedMilliseconds, longestWait;
    unsigned long waitsOverThreshold;
    BOOL heldByMain;
} Holding;

typedef struct {
    const void *locks[MAX_HELD];
    unsigned count;
    // -[NSConditionLock lockWhenCondition:] calls -lock on itself, so without
    // this the same acquisition is counted twice and the depth climbs for ever.
    // Only the outermost call on this thread is accounted for.
    unsigned inside;
} Held;

static os_unfair_lock ledger = OS_UNFAIR_LOCK_INIT;
static CFMutableDictionaryRef holdings;        // lock address -> Holding *
static NSMutableSet<NSString *> *pairsSeen;
static NSMutableSet<NSString *> *inversionsReported;
static pthread_key_t heldKey;
static double thresholdMilliseconds = 250;
static double nanosecondsPerTick = 1;

static double millisecondsSince(uint64_t then) {
    return (double)(mach_absolute_time() - then) * nanosecondsPerTick / 1e6;
}

static void copyThreadName(char *into, size_t size) {
    into[0] = 0;
    if (pthread_getname_np(pthread_self(), into, size) != 0 || !into[0])
        snprintf(into, size, pthread_main_np() ? "main" : "%p", (void *)pthread_self());
    else if (pthread_main_np())
        snprintf(into, size, "main");
}

// The frames of the application itself, innermost first, with this probe and the
// objc runtime dropped: enough to say where a lock is taken.
static NSString *whereWeAre(unsigned howMany) {
    void *frames[24];
    int count = backtrace(frames, 24);
    char **symbols = backtrace_symbols(frames, count);
    if (!symbols) return @"?";
    NSMutableArray *named = [NSMutableArray array];
    for (int i = 2; i < count && named.count < howMany; i++) {
        NSString *frame = @(symbols[i]);
        if ([frame containsString:@"lock-probe"] || [frame containsString:@"libobjc"]) continue;
        NSRange bracket = [frame rangeOfString:@" -[" options:NSBackwardsSearch];
        if (bracket.location == NSNotFound)
            bracket = [frame rangeOfString:@" +[" options:NSBackwardsSearch];
        NSString *name;
        if (bracket.location == NSNotFound) {
            // A C function: the fourth column of a backtrace_symbols line.
            NSArray *columns = [frame componentsSeparatedByString:@" "];
            NSMutableArray *kept = [NSMutableArray array];
            for (NSString *column in columns) if (column.length) [kept addObject:column];
            if (kept.count <= 3) continue;
            name = kept[3];
        } else {
            name = [frame substringFromIndex:bracket.location + 1];
            NSRange plus = [name rangeOfString:@" + " options:NSBackwardsSearch];
            if (plus.location != NSNotFound) name = [name substringToIndex:plus.location];
        }
        [named addObject:name];
    }
    free(symbols);
    return named.count ? [named componentsJoinedByString:@" <- "] : @"?";
}

// Called once per lock, while it is certainly still alive.
static CFStringRef identityOf(id lock) {
    static const char *symbols[] = {"PapyrusLock", "STORESCP", "STORESCPTLS"};
    for (unsigned i = 0; i < sizeof symbols / sizeof *symbols; i++) {
        void **slot = dlsym(RTLD_DEFAULT, symbols[i]);
        if (slot && *slot == (__bridge void *)lock)
            return CFBridgingRetain(@(symbols[i]));
    }
    return CFBridgingRetain([NSString stringWithFormat:@"%@ first taken in %@",
                             NSStringFromClass([lock class]), whereWeAre(3)]);
}

static Held *heldByThisThread(void) {
    Held *held = pthread_getspecific(heldKey);
    if (!held) {
        held = calloc(1, sizeof(Held));
        pthread_setspecific(heldKey, held);
    }
    return held;
}

// Both arguments are identity strings, not lock objects: thousands of per-image
// locks share one identity, and one line about the pair is the whole report.
static void noteOrder(NSString *outer, NSString *inner) {
    if ([outer isEqualToString:inner]) return;
    NSString *pair = [NSString stringWithFormat:@"%@||%@", outer, inner];
    NSString *opposite = [NSString stringWithFormat:@"%@||%@", inner, outer];
    BOOL inverted = NO;
    os_unfair_lock_lock(&ledger);
    [pairsSeen addObject:pair];
    if ([pairsSeen containsObject:opposite] && ![inversionsReported containsObject:pair] &&
        ![inversionsReported containsObject:opposite]) {
        [inversionsReported addObject:pair];
        inverted = YES;
    }
    os_unfair_lock_unlock(&ledger);
    if (inverted) {
        char name[64];
        copyThreadName(name, sizeof name);
        NSLog(@"LOCK116 order on %s: (%@) then (%@); the other way round elsewhere. Here: %@",
              name, outer, inner, whereWeAre(6));
    }
}

static void acquired(id lock, uint64_t waitedFrom) {
    const void *address = (__bridge const void *)lock;
    double waited = millisecondsSince(waitedFrom);
    Held *held = heldByThisThread();
    const void *outerAddress = held->count ? held->locks[held->count - 1] : NULL;

    os_unfair_lock_lock(&ledger);
    Holding *holding = (Holding *)CFDictionaryGetValue(holdings, address);
    os_unfair_lock_unlock(&ledger);
    if (!holding) {
        // Symbolising a stack is far too slow to do while the ledger is locked.
        CFStringRef identity = identityOf(lock);
        os_unfair_lock_lock(&ledger);
        holding = (Holding *)CFDictionaryGetValue(holdings, address);
        if (!holding) {
            holding = calloc(1, sizeof(Holding));
            holding->identity = identity;
            CFDictionarySetValue(holdings, address, holding);
        } else {
            CFRelease(identity);
        }
        os_unfair_lock_unlock(&ledger);
    }

    NSString *outerIdentity = nil, *innerIdentity = nil;
    os_unfair_lock_lock(&ledger);
    // Only a recursive lock can be taken again while held, and only by the
    // thread that already has it, so depth is all that has to be looked at.
    if (holding->depth == 0) {
        copyThreadName(holding->owner, sizeof holding->owner);
        holding->since = mach_absolute_time();
        holding->depth = 1;
    } else {
        holding->depth++;
    }
    holding->acquisitions++;
    holding->waitedMilliseconds += waited;
    if (waited > holding->longestWait) holding->longestWait = waited;
    if (waited > thresholdMilliseconds) holding->waitsOverThreshold++;
    if (pthread_main_np()) holding->heldByMain = YES;
    innerIdentity = (__bridge NSString *)holding->identity;
    if (outerAddress) {
        Holding *outer = (Holding *)CFDictionaryGetValue(holdings, outerAddress);
        if (outer) outerIdentity = (__bridge NSString *)outer->identity;
    }
    os_unfair_lock_unlock(&ledger);

    if (held->count < MAX_HELD) held->locks[held->count++] = address;
    if (outerIdentity) noteOrder(outerIdentity, innerIdentity);
    if (waited > thresholdMilliseconds) {
        char name[64];
        copyThreadName(name, sizeof name);
        NSLog(@"LOCK116 waited %.0f ms on %s for %@", waited, name, innerIdentity);
    }
}

static void releasing(id lock) {
    const void *address = (__bridge const void *)lock;
    double heldFor = -1;
    NSString *identity = nil;
    os_unfair_lock_lock(&ledger);
    Holding *holding = (Holding *)CFDictionaryGetValue(holdings, address);
    if (holding && holding->depth) {
        if (--holding->depth == 0) {
            heldFor = millisecondsSince(holding->since);
            holding->heldMilliseconds += heldFor;
            if (heldFor > holding->longestHold) holding->longestHold = heldFor;
            identity = (__bridge NSString *)holding->identity;
        }
    }
    os_unfair_lock_unlock(&ledger);

    Held *held = heldByThisThread();
    for (unsigned i = held->count; i > 0; i--)
        if (held->locks[i - 1] == address) {
            memmove(&held->locks[i - 1], &held->locks[i],
                    (held->count - i) * sizeof(const void *));
            held->count--;
            break;
        }
    if (heldFor > thresholdMilliseconds) {
        char name[64];
        copyThreadName(name, sizeof name);
        NSLog(@"LOCK116 held %.0f ms on %s: %@", heldFor, name, identity);
    }
}

// --- the swizzles -----------------------------------------------------------
typedef struct { Class cls; SEL selector; IMP original; } Hook;
static Hook hooks[24];
static unsigned hookCount;

static IMP originalFor(id self, SEL selector) {
    Class cls = object_getClass(self);
    for (unsigned i = 0; i < hookCount; i++)
        if (hooks[i].cls == cls && sel_isEqual(hooks[i].selector, selector))
            return hooks[i].original;
    return NULL;
}

static BOOL enterHook(void) {
    Held *held = heldByThisThread();
    if (held->inside) return NO;
    held->inside = 1;
    return YES;
}

static void leaveHook(BOOL entered) {
    if (entered) heldByThisThread()->inside = 0;
}

static void hookedLock(id self, SEL _cmd) {
    BOOL mine = enterHook();
    uint64_t started = mach_absolute_time();
    ((void (*)(id, SEL))originalFor(self, _cmd))(self, _cmd);
    if (mine) acquired(self, started);
    leaveHook(mine);
}

static void hookedUnlock(id self, SEL _cmd) {
    BOOL mine = enterHook();
    if (mine) releasing(self);
    ((void (*)(id, SEL))originalFor(self, _cmd))(self, _cmd);
    leaveHook(mine);
}

static BOOL hookedTryLock(id self, SEL _cmd) {
    BOOL mine = enterHook();
    uint64_t started = mach_absolute_time();
    BOOL got = ((BOOL (*)(id, SEL))originalFor(self, _cmd))(self, _cmd);
    if (got && mine) acquired(self, started);
    leaveHook(mine);
    return got;
}

static BOOL hookedLockBeforeDate(id self, SEL _cmd, NSDate *date) {
    BOOL mine = enterHook();
    uint64_t started = mach_absolute_time();
    BOOL got = ((BOOL (*)(id, SEL, NSDate *))originalFor(self, _cmd))(self, _cmd, date);
    if (got && mine) acquired(self, started);
    leaveHook(mine);
    return got;
}

static void hookedLockWhenCondition(id self, SEL _cmd, NSInteger condition) {
    BOOL mine = enterHook();
    uint64_t started = mach_absolute_time();
    ((void (*)(id, SEL, NSInteger))originalFor(self, _cmd))(self, _cmd, condition);
    if (mine) acquired(self, started);
    leaveHook(mine);
}

static BOOL hookedLockWhenConditionBeforeDate(id self, SEL _cmd, NSInteger condition, NSDate *date) {
    BOOL mine = enterHook();
    uint64_t started = mach_absolute_time();
    BOOL got = ((BOOL (*)(id, SEL, NSInteger, NSDate *))originalFor(self, _cmd))(self, _cmd,
                                                                                 condition, date);
    if (got && mine) acquired(self, started);
    leaveHook(mine);
    return got;
}

static void hookedUnlockWithCondition(id self, SEL _cmd, NSInteger condition) {
    BOOL mine = enterHook();
    if (mine) releasing(self);
    ((void (*)(id, SEL, NSInteger))originalFor(self, _cmd))(self, _cmd, condition);
    leaveHook(mine);
}

static void swizzle(Class cls, SEL selector, IMP replacement) {
    Method method = class_getInstanceMethod(cls, selector);
    if (!method || hookCount >= sizeof hooks / sizeof *hooks) return;
    hooks[hookCount].cls = cls;
    hooks[hookCount].selector = selector;
    hooks[hookCount].original = method_setImplementation(method, replacement);
    hookCount++;
}

// --- the standing report ----------------------------------------------------
static void *reporter(void *seconds) {
    pthread_setname_np("lock ledger");
    double interval = *(double *)seconds;
    free(seconds);
    while (1) {
        struct timespec sleepFor = {(time_t)interval, 0};
        nanosleep(&sleepFor, NULL);
        @autoreleasepool {
            NSMutableArray<NSString *> *standing = [NSMutableArray array];
            NSMutableDictionary<NSString *, NSMutableArray<NSNumber *> *> *totals =
                [NSMutableDictionary dictionary];

            os_unfair_lock_lock(&ledger);
            CFIndex count = CFDictionaryGetCount(holdings);
            const void **keys = calloc(count, sizeof(void *));
            const void **values = calloc(count, sizeof(void *));
            CFDictionaryGetKeysAndValues(holdings, keys, values);
            for (CFIndex i = 0; i < count; i++) {
                Holding *holding = (Holding *)values[i];
                NSString *identity = (__bridge NSString *)holding->identity;
                if (holding->depth)
                    [standing addObject:[NSString stringWithFormat:
                                         @"%@ held by %s for %.0f ms (depth %u)", identity,
                                         holding->owner, millisecondsSince(holding->since),
                                         holding->depth]];
                NSMutableArray *row = totals[identity];
                if (!row) totals[identity] = row = [@[@0, @0.0, @0.0, @0.0, @0.0, @0, @0] mutableCopy];
                row[0] = @([row[0] unsignedLongValue] + holding->acquisitions);
                row[1] = @([row[1] doubleValue] + holding->heldMilliseconds);
                row[2] = @(MAX([row[2] doubleValue], holding->longestHold));
                row[3] = @([row[3] doubleValue] + holding->waitedMilliseconds);
                row[4] = @(MAX([row[4] doubleValue], holding->longestWait));
                row[5] = @([row[5] unsignedLongValue] + holding->waitsOverThreshold);
                row[6] = @([row[6] boolValue] || holding->heldByMain);
            }
            free(keys);
            free(values);
            os_unfair_lock_unlock(&ledger);

            for (NSString *line in standing) NSLog(@"LOCK116 standing %@", line);
            NSArray *byHold = [totals.allKeys sortedArrayUsingComparator:
                               ^NSComparisonResult(NSString *a, NSString *b) {
                return [totals[b][1] compare:totals[a][1]];
            }];
            for (NSString *identity in [byHold subarrayWithRange:
                                        NSMakeRange(0, MIN(8u, (unsigned)byHold.count))]) {
                NSArray *row = totals[identity];
                if ([row[1] doubleValue] < 1 && [row[3] doubleValue] < 1) continue;
                NSLog(@"LOCK116 ledger taken %6lu, held %8.0f ms (longest %6.0f), waited %8.0f ms "
                      @"(longest %6.0f, %lu over the threshold)%@ %@",
                      [row[0] unsignedLongValue], [row[1] doubleValue], [row[2] doubleValue],
                      [row[3] doubleValue], [row[4] doubleValue], [row[5] unsignedLongValue],
                      [row[6] boolValue] ? @" [main has held it]" : @"", identity);
            }
        }
    }
    return NULL;
}

__attribute__((constructor)) static void install(void) {
    const char *enabled = getenv("HOROS_LOCK_MS");
    if (!enabled) return;
    // DYLD_INSERT_LIBRARIES reaches every child process a plugin starts; only
    // the application itself is being measured.
    if (![NSBundle.mainBundle.bundleIdentifier hasPrefix:@"org.horosproject.horos"]) return;
    thresholdMilliseconds = atof(enabled);
    if (thresholdMilliseconds <= 0) thresholdMilliseconds = 250;

    mach_timebase_info_data_t timebase;
    mach_timebase_info(&timebase);
    nanosecondsPerTick = (double)timebase.numer / (double)timebase.denom;

    holdings = CFDictionaryCreateMutable(NULL, 0, NULL, NULL);
    pairsSeen = [NSMutableSet set];
    inversionsReported = [NSMutableSet set];
    pthread_key_create(&heldKey, free);

    for (Class cls in @[NSLock.class, NSRecursiveLock.class, NSConditionLock.class]) {
        swizzle(cls, @selector(lock), (IMP)hookedLock);
        swizzle(cls, @selector(unlock), (IMP)hookedUnlock);
        swizzle(cls, @selector(tryLock), (IMP)hookedTryLock);
        swizzle(cls, @selector(lockBeforeDate:), (IMP)hookedLockBeforeDate);
    }
    swizzle(NSConditionLock.class, @selector(lockWhenCondition:), (IMP)hookedLockWhenCondition);
    swizzle(NSConditionLock.class, @selector(lockWhenCondition:beforeDate:),
            (IMP)hookedLockWhenConditionBeforeDate);
    swizzle(NSConditionLock.class, @selector(unlockWithCondition:), (IMP)hookedUnlockWithCondition);

    const char *report = getenv("HOROS_LOCK_REPORT");
    double interval = report ? atof(report) : 20;
    if (interval > 0) {
        double *seconds = malloc(sizeof(double));
        *seconds = interval;
        pthread_t thread;
        pthread_create(&thread, NULL, reporter, seconds);
        pthread_detach(thread);
    }
    NSLog(@"LOCK116 watching %u lock method(s), reporting waits and holds over %.0f ms",
          hookCount, thresholdMilliseconds);
}
