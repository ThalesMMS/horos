#import <Foundation/Foundation.h>

// Main-thread-owned request identities prevent stale unmount/remount results.
@interface HorosVolumeDiscovery : NSObject {
    NSOperationQueue *_queue;
    NSMutableDictionary *_tokens;
}
- (BOOL)discoverPath:(NSString *)path worker:(id (^)(void))worker completion:(void (^)(id))completion;
- (void)cancelPath:(NSString *)path;
- (void)cancelAll;
@end

@implementation HorosVolumeDiscovery
- (id)init {
    if ((self = [super init])) {
        _queue = [[NSOperationQueue alloc] init];
        _queue.maxConcurrentOperationCount = 2;
        _tokens = [[NSMutableDictionary alloc] init];
    }
    return self;
}
- (BOOL)discoverPath:(NSString *)path worker:(id (^)(void))worker completion:(void (^)(id))completion {
    NSAssert(NSThread.isMainThread, @"Volume requests belong to the main thread.");
    if (!path.length || !worker || !completion || [_tokens objectForKey:path]) return NO;
    NSUUID *token = NSUUID.UUID;
    [_tokens setObject:token forKey:path];
    [_queue addOperationWithBlock:^{
        @autoreleasepool {
            id result = nil;
            @try { result = worker(); }
            @catch (NSException *exception) { NSLog(@"Volume discovery failed: %@", exception.name); }
            dispatch_async(dispatch_get_main_queue(), ^{
                if ([[_tokens objectForKey:path] isEqual:token]) {
                    [_tokens removeObjectForKey:path];
                    completion(result);
                }
            });
        }
    }];
    return YES;
}
- (void)cancelPath:(NSString *)path {
    NSAssert(NSThread.isMainThread, @"Volume requests belong to the main thread.");
    if (path) [_tokens removeObjectForKey:path];
}
- (void)cancelAll {
    NSAssert(NSThread.isMainThread, @"Volume requests belong to the main thread.");
    [_tokens removeAllObjects];
    [_queue cancelAllOperations];
}
- (void)dealloc {
    [_queue cancelAllOperations];
    [_queue release];
    [_tokens release];
    [super dealloc];
}
@end
