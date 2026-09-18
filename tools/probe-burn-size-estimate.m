// Drives -[BurnerWindowController estimateFolderSize:] from the application's
// linked objects (#632): BurnerWindowController.o and DefaultsOsiriX.o as the
// app builds them, or both recompiled at another revision.
//
//   probe <cases.json>
//
// Each case names the files selected for the medium and the preferences the
// estimate reads; a preference left out of a case keeps the value the app
// registers for it (DefaultsOsiriX at the same revision). The probe prints, per
// case, the text the size field shows. Preferences live in memory only: the
// app's registration goes to the registration domain, each case's values to the
// argument domain, and the estimate's own writes are redirected there too, so
// nothing is written to any preferences file.
//
// Built without ARC, like the objects it links.
#import <Cocoa/Cocoa.h>
#include <objc/runtime.h>

// App classes the objects name; the estimate reaches none of them.
@interface Anonymization : NSObject @end
@implementation Anonymization @end
@interface AppController : NSObject @end
@implementation AppController @end
@interface BrowserController : NSObject @end
@implementation BrowserController @end
@interface DicomDatabase : NSObject @end
@implementation DicomDatabase @end
@interface DicomDir : NSObject @end
@implementation DicomDir @end
@interface DicomFile : NSObject @end
@implementation DicomFile @end
@interface DicomStudy : NSObject @end
@implementation DicomStudy @end
@interface Horos : NSObject @end
@implementation Horos @end
@interface HorosAnonymizationErrorPresenter : NSObject @end
@implementation HorosAnonymizationErrorPresenter @end
@interface ThreadsManager : NSObject @end
@implementation ThreadsManager @end
// +[DefaultsOsiriX getDefaults] registers the additional displayed storage classes with it.
@interface DCMAbstractSyntaxUID : NSObject @end
@implementation DCMAbstractSyntaxUID
+ (NSString *)MRSpectroscopyStorage { return @"1.2.840.10008.5.1.4.1.1.4.2"; }
@end

NSString *const OsirixWadoServiceEnabledDefaultsKey = @"wadoServer";
NSString *const OsirixWebPortalEnabledDefaultsKey = @"httpWebServer";
NSString *const OsirixWebPortalPortNumberDefaultsKey = @"httpWebServerPort";
NSString *const OsirixWebPortalPrefersFlashDefaultsKey = @"WebServerPrefersFlash";
NSString *const OsirixWebPortalUsesWeasisDefaultsKey = @"WebServerUsesWeasis";

@interface NSObject (BurnSizeProbe)
+ (NSMutableDictionary *)getDefaults;
- (IBAction)estimateFolderSize:(id)sender;
@end

static NSMutableDictionary *argumentDomain;

// -[NSUserDefaults setBool:forKey:] and friends, kept in the argument domain.
static void setInMemory(NSUserDefaults *defaults, SEL selector, id value, NSString *key) {
    if (value) argumentDomain[key] = value; else [argumentDomain removeObjectForKey:key];
    [defaults setVolatileDomain:argumentDomain forName:NSArgumentDomain];
}
static void setBoolInMemory(NSUserDefaults *defaults, SEL selector, BOOL value, NSString *key) {
    setInMemory(defaults, selector, @(value), key);
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc < 2) { fprintf(stderr, "usage: %s <cases.json>\n", argv[0]); return 64; }
        [NSApplication sharedApplication];
        NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
        method_setImplementation(class_getInstanceMethod(NSUserDefaults.class, @selector(setBool:forKey:)), (IMP)setBoolInMemory);
        method_setImplementation(class_getInstanceMethod(NSUserDefaults.class, @selector(setObject:forKey:)), (IMP)setInMemory);
        NSMutableDictionary *registered = [NSClassFromString(@"DefaultsOsiriX") getDefaults];
        NSMutableDictionary *registration = [NSMutableDictionary dictionary];
        for (NSString *key in @[@"BurnOsirixApplication", @"BurnWeasis", @"BurnSupplementaryFolder", @"SupplementaryBurnPath", @"BurnHtml"])
            if (registered[key]) registration[key] = registered[key];
        [defaults setVolatileDomain:registration forName:NSRegistrationDomain];

        NSArray *cases = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[1])] options:0 error:NULL];
        NSMutableArray *results = [NSMutableArray array];
        Class controllerClass = NSClassFromString(@"BurnerWindowController");
        for (NSDictionary *item in cases) {
            @autoreleasepool {
                argumentDomain = [[item[@"defaults"] mutableCopy] autorelease];
                [defaults setVolatileDomain:argumentDomain forName:NSArgumentDomain];
                // The window controller's own initialisers load the window and
                // clear the burn folder; the estimate only needs its file list
                // and the size field.
                id controller = [controllerClass alloc];
                NSTextField *field = [[[NSTextField alloc] initWithFrame:NSMakeRect(0, 0, 400, 20)] autorelease];
                object_setIvar(controller, class_getInstanceVariable(controllerClass, "files"), [item[@"files"] mutableCopy]);
                object_setIvar(controller, class_getInstanceVariable(controllerClass, "sizeField"), field);
                [controller estimateFolderSize:nil];
                [results addObject:@{@"name": item[@"name"], @"text": field.stringValue,
                                     @"registered_launcher": registration[@"BurnOsirixApplication"] ?: [NSNull null]}];
            }
        }
        NSData *data = [NSJSONSerialization dataWithJSONObject:results options:0 error:NULL];
        fwrite(data.bytes, 1, data.length, stdout);
        fputc('\n', stdout);
    }
    return 0;
}
