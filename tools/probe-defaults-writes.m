// Diagnostic-only probe: say who writes a given preference key, and from where.
//
//   clang -shared -fobjc-arc -framework Cocoa tools/probe-defaults-writes.m \
//     -o <dir>/defaults-probe.dylib && codesign --force --sign - <dir>/defaults-probe.dylib
//
// HOROS_WATCH_DEFAULT=<key>[,<key>...]. Every -[NSUserDefaults setObject:forKey:]
// and -setPersistentDomain:forName: that mentions one of those keys is logged
// with the call stack that made it, so a key that arrives in the persistent
// domain without anybody meaning to put it there can be traced to its line.
// Nothing is changed: each call is passed straight through.
#import <Cocoa/Cocoa.h>
#import <objc/runtime.h>

static NSArray<NSString *> *watched;

static void report(NSString *what, NSString *key, id value) {
    NSLog(@"DEFAULTS278 %@ %@ = %@", what, key, value);
    for (NSString *frame in NSThread.callStackSymbols) NSLog(@"DEFAULTS278   %@", frame);
}

static void (*originalSetObject)(id, SEL, id, NSString *);
static void hookedSetObject(id self, SEL _cmd, id value, NSString *key) {
    if ([watched containsObject:key]) report(@"setObject:forKey:", key, value);
    originalSetObject(self, _cmd, value, key);
}

static void (*originalSetPersistentDomain)(id, SEL, NSDictionary *, NSString *);
static void hookedSetPersistentDomain(id self, SEL _cmd, NSDictionary *domain, NSString *name) {
    for (NSString *key in watched)
        if (domain[key]) report(([NSString stringWithFormat:@"setPersistentDomain: %@", name]),
                                key, domain[key]);
    originalSetPersistentDomain(self, _cmd, domain, name);
}

__attribute__((constructor)) static void install(void) {
    const char *keys = getenv("HOROS_WATCH_DEFAULT");
    if (!keys) return;
    watched = [@(keys) componentsSeparatedByString:@","];
    NSLog(@"DEFAULTS278 watching %@", [watched componentsJoinedByString:@", "]);

    Method setObject = class_getInstanceMethod(NSUserDefaults.class, @selector(setObject:forKey:));
    if (setObject) originalSetObject = (void *)method_setImplementation(setObject, (IMP)hookedSetObject);
    Method setDomain = class_getInstanceMethod(NSUserDefaults.class, @selector(setPersistentDomain:forName:));
    if (setDomain) originalSetPersistentDomain = (void *)method_setImplementation(setDomain,
                                                                                 (IMP)hookedSetPersistentDomain);
}
