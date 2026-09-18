// Two development apps sharing a database (#637): one serves it, the other opens
// it as a remote database through RemoteDicomDatabase, the way the browser does.
// Injected with DYLD_INSERT_LIBRARIES and driven by numbered command files.
//
//   HOROS_PAIR_ROLE      server | client
//   HOROS_PAIR_COMMANDS  a folder: <n>.json is run for n = 1, 2, ... in order, and
//                        answered in <n>.out.json (written whole, then renamed)
//
// Both roles:
//   {"action": "ping"}
// Server:
//   {"action": "link", "paths": [...]}
//       File > Import (-[BrowserController addFilesAndFolderToDatabase:]); the app
//       is launched with COPYDATABASE NO, so the images are linked in place
//   {"action": "report", "study": "<StudyInstanceUID>", "path": "..."}
//       the study's reportURL set in the index, as a report opened from elsewhere
// Client:
//   {"action": "open", "port": n, "password": "..."}
//       -[RemoteDicomDatabase initWithHost:port:update:] then -update, off the main
//       thread; answered once the index is loaded: its studies and images
//   {"action": "images"}
//       every image of the remote index: SOP instance, study, the path the server
//       gave (what the client asks for), whether it is in the database folder
//   {"action": "download", "sops": [...]}
//       -cacheDataForImage:maxFiles:1 for each: the local path, bytes and SHA-256
//   {"action": "set", "study" or "sop": "...", "key": "...", "value": ...}
//       -object:setValue:forKey: on the study or image
//   {"action": "album", "study": "...", "album": "<name>", "add": bool}
//       -addStudies:toAlbum: or -removeStudies:fromAlbum:
//   {"action": "albums"}
//       the regular albums of the remote index
//   {"action": "send", "sops": [...], "aet": "...", "address": "...", "port": n}
//       -storeScuImages:toDestinationAETitle:address:port:transferSyntax:
//
//   xcrun clang -dynamiclib -fobjc-arc -framework Cocoa -framework CoreData \
//       tools/probe-shared-database-pair.m -o probe-shared-database-pair.dylib
#import <Cocoa/Cocoa.h>
#import <CoreData/CoreData.h>
#include <CommonCrypto/CommonDigest.h>

@interface NSObject (SharedDatabasePairProbe)
+ (id)currentBrowser;
+ (id)defaultDatabase;
- (void)addFilesAndFolderToDatabase:(NSArray *)paths;
- (NSManagedObjectContext *)managedObjectContext;
- (id)initWithHost:(NSHost *)host port:(NSInteger)port update:(BOOL)update;
- (void)update;
- (NSString *)cacheDataForImage:(id)image maxFiles:(NSInteger)maxFiles;
- (void)object:(NSManagedObject *)object setValue:(id)value forKey:(NSString *)key;
- (void)addStudies:(NSArray *)studies toAlbum:(id)album;
- (void)removeStudies:(NSArray *)studies fromAlbum:(id)album;
- (void)storeScuImages:(NSArray *)images toDestinationAETitle:(NSString *)aet address:(NSString *)address port:(NSInteger)port
        transferSyntax:(int)syntax;
- (BOOL)save:(NSError **)error;
@end

static id remote = nil;

static id onMain(id (^block)(void)) {
    __block id result = nil;
    if ([NSThread isMainThread]) return block();
    dispatch_sync(dispatch_get_main_queue(), ^{ result = block(); });
    return result;
}

static NSArray *fetch(NSManagedObjectContext *context, NSString *entity, NSPredicate *predicate) {
    NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:entity];
    request.predicate = predicate;
    return [context executeFetchRequest:request error:NULL] ?: @[];
}

static NSString *sha256(NSData *data) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
    NSMutableString *hex = [NSMutableString string];
    for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) [hex appendFormat:@"%02x", digest[i]];
    return hex;
}

static NSDictionary *serverCommand(NSDictionary *command) {
    NSString *action = command[@"action"];
    if ([action isEqualToString:@"link"]) {
        return onMain(^id {
            [[NSClassFromString(@"BrowserController") currentBrowser] addFilesAndFolderToDatabase:command[@"paths"]];
            return @{@"ok": @YES};
        });
    }
    if ([action isEqualToString:@"report"]) {
        return onMain(^id {
            NSManagedObjectContext *context = [[NSClassFromString(@"DicomDatabase") defaultDatabase] managedObjectContext];
            NSManagedObject *study = fetch(context, @"Study", [NSPredicate predicateWithFormat:@"studyInstanceUID == %@", command[@"study"]]).firstObject;
            if (!study) return @{@"error": @"no such study"};
            [study setValue:command[@"path"] forKey:@"reportURL"];
            NSError *error = nil;
            BOOL saved = [context save:&error];
            return @{@"ok": @(saved), @"error": error ? error.localizedDescription : [NSNull null]};
        });
    }
    return @{@"error": [NSString stringWithFormat:@"unknown server action %@", action]};
}

static NSManagedObjectContext *remoteContext(void) { return [remote managedObjectContext]; }

// The index stores the SOP instance UID compressed: images are matched in memory.
static NSArray *remoteImages(NSArray *sops) {
    return [fetch(remoteContext(), @"Image", nil) filteredArrayUsingPredicate:[NSPredicate predicateWithFormat:@"sopInstanceUID IN %@", sops]];
}

static NSManagedObject *remoteObject(NSDictionary *command) {
    if (command[@"study"])
        return fetch(remoteContext(), @"Study", [NSPredicate predicateWithFormat:@"studyInstanceUID == %@", command[@"study"]]).firstObject;
    return remoteImages(@[command[@"sop"] ?: @""]).firstObject;
}

static NSDictionary *clientCommand(NSDictionary *command) {
    NSString *action = command[@"action"];
    if ([action isEqualToString:@"open"]) {
        @try {
            id database = [[NSClassFromString(@"RemoteDicomDatabase") alloc] initWithHost:[NSHost hostWithAddress:@"127.0.0.1"]
                                                                                     port:[command[@"port"] integerValue] update:NO];
            [database setValue:command[@"password"] forKey:@"password"];
            [database update];
            remote = database;
        } @catch (NSException *exception) {
            return @{@"error": [NSString stringWithFormat:@"%@: %@", exception.name, exception.reason]};
        }
        for (int wait = 0; wait < 600; wait++) {
            NSDictionary *counts = onMain(^id {
                return @{@"studies": @(fetch(remoteContext(), @"Study", nil).count), @"images": @(fetch(remoteContext(), @"Image", nil).count)};
            });
            if ([counts[@"images"] integerValue] > 0) return counts;
            usleep(100 * 1000);
        }
        return @{@"error": @"the remote index never loaded"};
    }
    if (!remote) return @{@"error": @"no remote database"};
    if ([action isEqualToString:@"images"]) {
        return onMain(^id {
            NSMutableArray *images = [NSMutableArray array];
            for (NSManagedObject *image in fetch(remoteContext(), @"Image", nil))
                [images addObject:@{@"sop": [image valueForKey:@"sopInstanceUID"] ?: @"",
                                    @"study": [image valueForKeyPath:@"series.study.studyInstanceUID"] ?: @"",
                                    @"path": [image valueForKey:@"path"] ?: @"",
                                    @"inDatabaseFolder": [image valueForKey:@"inDatabaseFolder"] ?: @NO}];
            return @{@"images": images};
        });
    }
    if ([action isEqualToString:@"download"]) {
        return onMain(^id {
            NSMutableArray *files = [NSMutableArray array];
            for (NSManagedObject *image in remoteImages(command[@"sops"])) {
                NSString *path = nil;
                NSString *failure = nil;
                @try {
                    path = [remote cacheDataForImage:image maxFiles:1];
                } @catch (NSException *exception) {
                    failure = exception.reason ?: exception.name;
                }
                NSData *data = path ? [NSData dataWithContentsOfFile:path] : nil;
                [files addObject:@{@"sop": [image valueForKey:@"sopInstanceUID"] ?: @"", @"path": path ?: [NSNull null],
                                   @"bytes": @(data.length), @"sha256": data ? sha256(data) : [NSNull null],
                                   @"error": failure ?: [NSNull null]}];
            }
            return @{@"files": files};
        });
    }
    if ([action isEqualToString:@"set"]) {
        return onMain(^id {
            NSManagedObject *object = remoteObject(command);
            if (!object) return @{@"error": @"no such object"};
            id value = command[@"value"] == [NSNull null] ? nil : command[@"value"];
            [remote object:object setValue:value forKey:command[@"key"]];
            return @{@"ok": @YES};
        });
    }
    if ([action isEqualToString:@"albums"]) {
        return onMain(^id {
            NSMutableArray *names = [NSMutableArray array];
            for (NSManagedObject *album in fetch(remoteContext(), @"Album", [NSPredicate predicateWithFormat:@"smartAlbum == NO"]))
                [names addObject:[album valueForKey:@"name"] ?: @""];
            return @{@"albums": names};
        });
    }
    if ([action isEqualToString:@"album"]) {
        return onMain(^id {
            NSManagedObject *study = remoteObject(command);
            NSManagedObject *album = fetch(remoteContext(), @"Album", [NSPredicate predicateWithFormat:@"name == %@", command[@"album"]]).firstObject;
            if (!study || !album) return @{@"error": @"no such study or album"};
            if ([command[@"add"] boolValue]) [remote addStudies:@[study] toAlbum:album];
            else [remote removeStudies:@[study] fromAlbum:album];
            return @{@"ok": @YES};
        });
    }
    if ([action isEqualToString:@"send"]) {
        return onMain(^id {
            [remote storeScuImages:remoteImages(command[@"sops"]) toDestinationAETitle:command[@"aet"] address:command[@"address"]
                              port:[command[@"port"] integerValue] transferSyntax:0];
            return @{@"ok": @YES};
        });
    }
    return @{@"error": [NSString stringWithFormat:@"unknown client action %@", action]};
}

__attribute__((constructor)) static void installSharedDatabasePairProbe(void) {
    NSDictionary *environment = NSProcessInfo.processInfo.environment;
    NSString *folder = environment[@"HOROS_PAIR_COMMANDS"], *role = environment[@"HOROS_PAIR_ROLE"];
    if (!folder || !role) return;
    unsetenv("DYLD_INSERT_LIBRARIES");
    BOOL server = [role isEqualToString:@"server"];
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
                        if (!command) answer = @{@"error": @"unreadable command"};
                        else if ([command[@"action"] isEqualToString:@"ping"]) answer = @{@"ok": @YES, @"role": role};
                        else answer = server ? serverCommand(command) : clientCommand(command);
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
