#import "HorosPluginCatalog.h"
#include <math.h>

static inline NSError *HorosPluginCatalogError(NSInteger code, NSString *message)
{
    return [NSError errorWithDomain:@"HorosPluginCatalog" code:code userInfo:@{NSLocalizedDescriptionKey:message}];
}

// The existing preload worker owns this synchronous boundary. UI callers use cache only.
static inline NSArray *HorosLoadPluginCatalog(NSURL *url, NSTimeInterval timeout, NSError **error)
{
    if (error) *error = nil;
    if (NSThread.isMainThread || !HorosPluginHTTPURL(url.absoluteString)) {
        if (error) *error = HorosPluginCatalogError(1, NSLocalizedString(@"The plugin catalog request is invalid.", nil));
        return nil;
    }
#if DEBUG
    // Development-only loopback fixture; never redirects production builds or remote hosts.
    NSDictionary *environment = NSProcessInfo.processInfo.environment;
    NSURL *fixture = HorosPluginHTTPURL(environment[@"HOROS_PLUGIN_CATALOG_TEST_URL"]);
    if (fixture && ([@[@"127.0.0.1", @"localhost", @"::1"] containsObject:fixture.host])) {
        url = fixture;
        double fixtureTimeout = [environment[@"HOROS_PLUGIN_CATALOG_TEST_TIMEOUT"] doubleValue];
        if (isfinite(fixtureTimeout) && fixtureTimeout >= 0.1 && fixtureTimeout <= 10) timeout = fixtureTimeout;
    }
#endif
    timeout = isfinite(timeout) && timeout > 0 ? timeout : 10;
    NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    configuration.timeoutIntervalForRequest = timeout;
    configuration.timeoutIntervalForResource = timeout;
    configuration.HTTPCookieStorage = nil;
    configuration.URLCache = nil;
    NSURLSession *session = [NSURLSession sessionWithConfiguration:configuration];
    NSMutableDictionary *result = [NSMutableDictionary dictionary];
    dispatch_semaphore_t finished = dispatch_semaphore_create(0);
    NSURLSessionDataTask *task = [session dataTaskWithURL:url completionHandler:^(NSData *data, NSURLResponse *response, NSError *failure) {
        @synchronized(result) {
            if (data) result[@"data"] = data;
            if (response) result[@"response"] = response;
            if (failure) result[@"error"] = failure;
        }
        dispatch_semaphore_signal(finished);
    }];
    [task resume];
    dispatch_semaphore_wait(finished, DISPATCH_TIME_FOREVER);
    [session finishTasksAndInvalidate];
    dispatch_release(finished);
    NSError *failure = result[@"error"];
    if (failure) {
        if (error) *error = failure;
        return nil;
    }
    NSHTTPURLResponse *response = result[@"response"];
    NSInteger status = [response isKindOfClass:NSHTTPURLResponse.class] ? response.statusCode : 0;
    if (status < 200 || status >= 300) {
        if (error) *error = HorosPluginCatalogError(2, [NSString stringWithFormat:NSLocalizedString(@"The plugin catalog server returned HTTP %ld.", nil), (long)status]);
        return nil;
    }
    NSData *data = result[@"data"];
    id decoded = data.length ? [NSPropertyListSerialization propertyListWithData:data options:NSPropertyListImmutable format:NULL error:NULL] : nil;
    if (!decoded && data.length) decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
    NSArray *catalog = HorosValidatedPluginCatalog(decoded);
    if (!catalog && error) *error = HorosPluginCatalogError(3, NSLocalizedString(@"The plugin catalog response is malformed or contains no valid entries.", nil));
    return catalog;
}
