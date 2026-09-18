// The shared-database server of the application, headless (#614, #615).
//
// Links the objects the app is built from - BonjourPublisher.o (the
// O2DatabaseConnection parser), HorosDatabaseServer.o (its Network.framework
// listener since #615), N2Connection.o and N2ConnectionListener.o (its listener
// before #615, for a baseline revision), N2Locker.o and the Swift rules it asks
// - and serves requests the way that revision does, replacing the database, browser
// and app controller with recorders. Every effect a request can have on the
// database is printed as one JSON line on stdout, so a client can check that a
// fragmented request mutates exactly once and an invalid one not at all.
//
//   probe <port> <scratch folder>
//   env HOROS_PROBE_PASSWORD=<password>  protect the database with that password
//
// <scratch folder>/index.json, read at each use, stands for what the index holds
// (#637): {"linked": [absolute paths images are linked to],
//          "values": {"<object id>": {"<key>": value}}} - the values an object
// answers before anything is written to it.
//
// stdin accepts "threads" (prints the process thread count) and "quit".
// Built without ARC, like the objects it links.
#import <Cocoa/Cocoa.h>
#include <mach/mach.h>
#include <pthread.h>

static NSString *scratchFolder;
static pthread_mutex_t emitLock = PTHREAD_MUTEX_INITIALIZER;

static void emit(NSDictionary *event) {
    // Benchmarks keep the recorder quiet: only the kind of event is written.
    if (getenv("HOROS_PROBE_QUIET") && ![event[@"event"] isEqual:@"ready"] && ![event[@"event"] isEqual:@"threads"])
        event = @{@"event": event[@"event"]};
    NSData *data = [NSJSONSerialization dataWithJSONObject:event options:0 error:NULL];
    pthread_mutex_lock(&emitLock);
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
    fflush(stdout);
    pthread_mutex_unlock(&emitLock);
}

static id orNull(id value) { return value ?: [NSNull null]; }

static NSDictionary *indexDocument(void) {
    NSData *data = [NSData dataWithContentsOfFile:[scratchFolder stringByAppendingPathComponent:@"index.json"]];
    return data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL] : @{};
}

// Preference keys BonjourPublisher.o links against.
NSString * const OsirixBonjourSharingIsActiveDefaultsKey = @"bonjourSharing";
NSString * const OsirixBonjourSharingNameDefaultsKey = @"bonjourServiceName";
NSString * const OsirixBonjourSharingIsPasswordProtectedDefaultsKey = @"bonjourPasswordProtected";
NSString * const OsirixBonjourSharingPasswordDefaultsKey = @"bonjourPassword";

@implementation NSUserDefaults (SharedDatabaseProbe)
+ (BOOL)bonjourSharingIsActive { return YES; }
+ (BOOL)bonjourSharingIsPasswordProtected { return getenv("HOROS_PROBE_PASSWORD") != NULL; }
+ (NSString *)bonjourSharingPassword {
    const char *password = getenv("HOROS_PROBE_PASSWORD");
    return password ? @(password) : nil;
}
+ (NSString *)bonjourSharingName { return @"probe"; }
@end

@interface HorosBonjourAdvertisement : NSObject @end
@implementation HorosBonjourAdvertisement @end
@interface HorosListenBindFailure : NSObject @end
@implementation HorosListenBindFailure
+ (NSString *)databaseSharingService { return @"database sharing"; }
@end

@interface DCMTKStoreSCU : NSObject @end
@implementation DCMTKStoreSCU
+ (int)sendSyntaxForListenerSyntax:(int)syntax { return syntax; }
@end

// What -objectWithID: hands back: records every write, answers every read.
@interface ProbeObject : NSObject { NSString *_identifier; NSMutableDictionary *_values; }
- (instancetype)initWithIdentifier:(NSString *)identifier;
- (NSString *)probeIdentifier;
@end

@interface ProbeRelation : NSObject { NSString *_owner, *_key; }
- (instancetype)initWithOwner:(NSString *)owner key:(NSString *)key;
@end
@implementation ProbeObject
- (instancetype)initWithIdentifier:(NSString *)identifier {
    if ((self = [super init])) {
        _identifier = [identifier copy];
        _values = [indexDocument()[@"values"][identifier] mutableCopy] ?: [NSMutableDictionary new];
    }
    return self;
}
- (void)dealloc { [_identifier release]; [_values release]; [super dealloc]; }
- (id)valueForKeyPath:(NSString *)keyPath { return _values[keyPath] ?: @"previous"; }
- (id)valueForKey:(NSString *)key { return _values[key]; }
- (void)setValue:(id)value forKey:(NSString *)key { [self setValue:value forKeyPath:key]; }
- (void)setValue:(id)value forKeyPath:(NSString *)keyPath {
    if (value) _values[keyPath] = value; else [_values removeObjectForKey:keyPath];
    emit(@{@"event": @"setValue", @"object": _identifier, @"key": orNull(keyPath), @"value": orNull(value)});
}
- (NSMutableSet *)mutableSetValueForKey:(NSString *)key {
    return (NSMutableSet *)[[[ProbeRelation alloc] initWithOwner:_identifier key:key] autorelease];
}
- (void)archiveAnnotationsAsDICOMSR { emit(@{@"event": @"archiveAnnotations", @"object": _identifier}); }
- (NSNumber *)pathNumber { return @([[_identifier lastPathComponent] intValue]); }
- (NSString *)probeIdentifier { return _identifier; }
@end

@implementation ProbeRelation
- (instancetype)initWithOwner:(NSString *)owner key:(NSString *)key {
    if ((self = [super init])) { _owner = [owner copy]; _key = [key copy]; }
    return self;
}
- (void)dealloc { [_owner release]; [_key release]; [super dealloc]; }
- (void)addObject:(ProbeObject *)object {
    emit(@{@"event": @"relationAdd", @"owner": _owner, @"key": _key, @"object": [object probeIdentifier]});
}
- (void)removeObject:(ProbeObject *)object {
    emit(@{@"event": @"relationRemove", @"owner": _owner, @"key": _key, @"object": [object probeIdentifier]});
}
@end

@interface ProbeCoordinator : NSRecursiveLock @end
@implementation ProbeCoordinator @end
@interface ProbeContext : NSObject @end
@implementation ProbeContext
// The server asks for the paths images are linked to (#637); the fetch is recorded.
- (NSArray *)executeFetchRequest:(NSFetchRequest *)request error:(NSError **)error {
    emit(@{@"event": @"fetch", @"entity": orNull(request.entityName), @"predicate": orNull(request.predicate.predicateFormat)});
    NSMutableArray *rows = [NSMutableArray array];
    for (NSString *path in indexDocument()[@"linked"]) [rows addObject:@{@"pathString": path}];
    return request.predicate ? [rows filteredArrayUsingPredicate:request.predicate] : rows;
}
- (id)persistentStoreCoordinator {
    static ProbeCoordinator *coordinator;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ coordinator = [ProbeCoordinator new]; });
    return coordinator;
}
@end

@interface DicomDatabase : NSObject @end
@implementation DicomDatabase
+ (instancetype)defaultDatabase {
    static DicomDatabase *database;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ database = [DicomDatabase new]; });
    return database;
}
+ (instancetype)activeLocalDatabase { return [self defaultDatabase]; }
- (instancetype)independentDatabase { return self; }
- (id)managedObjectContext { static ProbeContext *context; if (!context) context = [ProbeContext new]; return context; }
- (BOOL)save { emit(@{@"event": @"save"}); return YES; }
- (BOOL)save:(NSError **)error { emit(@{@"event": @"save"}); return YES; }
- (NSString *)sqlFilePath { return [scratchFolder stringByAppendingPathComponent:@"Database.sql"]; }
- (NSString *)baseDirPath { return scratchFolder; }
- (NSString *)reportsDirPath { return [scratchFolder stringByAppendingPathComponent:@"REPORTS"]; }
- (NSString *)dataDirPath { return [scratchFolder stringByAppendingPathComponent:@"DATABASE.noindex"]; }
- (NSTimeInterval)timeOfLastModification { return 1234.5; }
- (id)objectWithID:(NSString *)identifier {
    emit(@{@"event": @"objectWithID", @"id": orNull(identifier)});
    return identifier ? [[[ProbeObject alloc] initWithIdentifier:identifier] autorelease] : nil;
}
- (NSString *)uniquePathForNewDataFileWithExtension:(NSString *)extension {
    static int counter = 0;
    NSString *uploads = [scratchFolder stringByAppendingPathComponent:@"uploads"];
    [[NSFileManager defaultManager] createDirectoryAtPath:uploads withIntermediateDirectories:YES attributes:nil error:NULL];
    return [uploads stringByAppendingPathComponent:[NSString stringWithFormat:@"%d.%@", ++counter, extension]];
}
- (NSArray *)addFilesAtPaths:(NSArray *)paths postNotifications:(BOOL)post dicomOnly:(BOOL)dicomOnly rereadExistingItems:(BOOL)reread generatedByOsiriX:(BOOL)generated {
    NSMutableArray *digests = [NSMutableArray array];
    for (NSString *path in paths) [digests addObject:@([[NSData dataWithContentsOfFile:path] length])];
    emit(@{@"event": @"addFiles", @"paths": paths, @"sizes": digests, @"generatedByOsiriX": @(generated)});
    NSMutableArray *identifiers = [NSMutableArray array];
    for (NSUInteger i = 0; i < paths.count; i++) [identifiers addObject:[NSString stringWithFormat:@"x-coredata://probe/Image/%lu", (unsigned long)i + 1]];
    return identifiers;
}
- (NSArray *)objectsWithIDs:(NSArray *)identifiers {
    NSMutableArray *objects = [NSMutableArray array];
    for (NSString *identifier in identifiers) [objects addObject:[[[ProbeObject alloc] initWithIdentifier:identifier] autorelease]];
    return objects;
}
@end

@interface BrowserController : NSObject @end
@implementation BrowserController
+ (instancetype)currentBrowser { static BrowserController *browser; if (!browser) browser = [BrowserController new]; return browser; }
+ (int)DefaultFolderSizeForDB { return 10000; }
- (DicomDatabase *)database { return [DicomDatabase defaultDatabase]; }
- (void)refreshDatabase:(id)sender {}
@end

@interface ProbePublisher : NSObject @end
@implementation ProbePublisher
- (void)sendDICOMFilesToOsiriXNode:(NSDictionary *)todo {
    emit(@{@"event": @"sendDICOMFiles", @"todo": todo});
}
@end

@interface AppController : NSObject @end
@implementation AppController
+ (instancetype)sharedAppController { static AppController *controller; if (!controller) controller = [AppController new]; return controller; }
- (id)bonjourPublisher { static ProbePublisher *publisher; if (!publisher) publisher = [ProbePublisher new]; return publisher; }
- (void)reportListenBindFailureForService:(NSString *)service port:(int)port errnoCode:(int)code {}
@end

@interface N2ConnectionListener : NSObject
- (instancetype)initWithPort:(NSInteger)port connectionClass:(Class)connectionClass;
- (void)setThreadPerConnection:(BOOL)value;
@end

static int threadCount(void);
static int threadCountForProbe(void) { return threadCount(); }

// The Network.framework server (#615), declared here without its generated header.
@interface HorosDatabaseServerStandIn : NSObject
- (instancetype)initWithPort:(uint16_t)port handler:(void (^)(id peer))handler;
- (void)setDelegate:(id)delegate;
- (void)start;
- (NSInteger)port;
@end
@interface O2DatabaseConnectionStandIn : NSObject
+ (void)servePeer:(id)peer;
@end

@interface ProbeServerDelegate : NSObject
@end
@implementation ProbeServerDelegate
- (void)databaseServerDidStart:(id)server {
    emit(@{@"event": @"ready", @"port": @([(HorosDatabaseServerStandIn *)server port]), @"threads": @(threadCountForProbe())});
}
- (void)databaseServer:(id)server didFailWithPOSIXError:(int)code description:(NSString *)description {
    emit(@{@"event": @"listenFailed", @"errno": @(code), @"description": description ?: @""});
    exit(3);
}
- (void)databaseServer:(id)server isWaitingWithPOSIXError:(int)code description:(NSString *)description {
    emit(@{@"event": @"listenWaiting", @"errno": @(code)});
}
@end

static int threadCount(void) {
    thread_act_array_t threads;
    mach_msg_type_number_t count;
    if (task_threads(mach_task_self(), &threads, &count) != KERN_SUCCESS) return -1;
    for (mach_msg_type_number_t i = 0; i < count; i++) mach_port_deallocate(mach_task_self(), threads[i]);
    vm_deallocate(mach_task_self(), (vm_address_t)threads, sizeof(thread_t) * count);
    return (int)count;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc < 3) { fprintf(stderr, "usage: %s <port> <scratch folder>\n", argv[0]); return 64; }
        scratchFolder = [@(argv[2]) retain];
        NSString *database = [DicomDatabase.defaultDatabase sqlFilePath];
        if (![[NSFileManager defaultManager] fileExistsAtPath:database])
            [[@"SQLite format 3" dataUsingEncoding:NSASCIIStringEncoding] writeToFile:database atomically:YES];
        Class connectionClass = NSClassFromString(@"O2DatabaseConnection");
        Class n2Connection = NSClassFromString(@"N2Connection");
        BOOL networkServer = !(n2Connection && [connectionClass isSubclassOfClass:n2Connection]);
        if (!networkServer) {
            // A revision before #615: a thread per connection.
            N2ConnectionListener *listener = [[N2ConnectionListener alloc] initWithPort:atoi(argv[1]) connectionClass:connectionClass];
            if (!listener) { emit(@{@"event": @"listenFailed"}); return 3; }
            [listener setThreadPerConnection:YES];
        } else {
            // Since #615: the listener the app starts, with the handler the app gives it.
            HorosDatabaseServerStandIn *server = [[NSClassFromString(@"HorosDatabaseServer") alloc]
                initWithPort:(uint16_t)atoi(argv[1]) handler:^(id peer) { [(Class)connectionClass servePeer:peer]; }];
            [server setDelegate:[ProbeServerDelegate new]];
            [server start]; // "ready" is emitted when the listener is
        }
        [NSThread detachNewThreadWithBlock:^{
            char line[256];
            while (fgets(line, sizeof line, stdin)) {
                if (strncmp(line, "threads", 7) == 0) emit(@{@"event": @"threads", @"count": @(threadCount())});
                if (strncmp(line, "quit", 4) == 0) exit(0);
            }
            exit(0);
        }];
        if (!networkServer)
            emit(@{@"event": @"ready", @"port": @(atoi(argv[1])), @"threads": @(threadCount())});
        [[NSRunLoop currentRunLoop] run];
    }
    return 0;
}
