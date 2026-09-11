#import <Foundation/Foundation.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

// Never reuse a caller-owned .temp folder or another anonymization's work files.
static inline NSString *HorosCreateAnonymizationStagingDirectory(NSString *parent, NSError **error)
{
    if (!parent.length) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:EINVAL userInfo:nil];
        return nil;
    }
    if (![[NSFileManager defaultManager] createDirectoryAtPath:parent withIntermediateDirectories:YES attributes:nil error:error])
        return nil;
    NSString *pattern = [parent stringByAppendingPathComponent:@".horos-anonymization-XXXXXX"];
    char *buffer = strdup(pattern.fileSystemRepresentation);
    if (!buffer) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:ENOMEM userInfo:nil];
        return nil;
    }
    NSString *result = nil;
    if (mkdtemp(buffer))
        result = [[NSFileManager defaultManager] stringWithFileSystemRepresentation:buffer length:strlen(buffer)];
    else if (error)
        *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
    free(buffer);
    return result;
}

// A replacement requires one distinct, nonempty output for every captured source.
// This is a preflight only; successful database import must also precede retirement.
static inline BOOL HorosAnonymizationOutputsComplete(NSArray *sources, NSDictionary *outputs)
{
    NSSet *sourceSet = [NSSet setWithArray:sources ?: @[]];
    if (!sourceSet.count || outputs.count != sourceSet.count ||
        ![sourceSet isEqualToSet:[NSSet setWithArray:outputs.allKeys]])
        return NO;
    NSMutableSet *canonicalSources = [NSMutableSet set];
    for (NSString *source in sources)
        [canonicalSources addObject:[[source stringByStandardizingPath] stringByResolvingSymlinksInPath]];
    NSMutableSet *destinations = [NSMutableSet set];
    for (NSString *output in outputs.allValues) {
        if (![output isKindOfClass:[NSString class]] || !output.length)
            return NO;
        NSString *canonical = [[output stringByStandardizingPath] stringByResolvingSymlinksInPath];
        if ([canonicalSources containsObject:canonical] || [destinations containsObject:canonical])
            return NO;
        NSDictionary *attributes = [[NSFileManager defaultManager] attributesOfItemAtPath:canonical error:NULL];
        if (![attributes.fileType isEqualToString:NSFileTypeRegular] || !attributes.fileSize)
            return NO;
        [destinations addObject:canonical];
    }
    return YES;
}

// One result for every requested input, including files skipped when a batch fails.
// These local paths are returned to the UI, never written to a shared log.
static inline NSArray *HorosAnonymizationFileResults(NSArray *sources, NSDictionary *failures, BOOL cancelled)
{
    NSMutableArray *results = [NSMutableArray arrayWithCapacity:sources.count];
    for (NSString *source in sources) {
        NSArray *reasons = [failures objectForKey:source];
        NSString *outcome = reasons.count ? @"failed" : (cancelled ? @"cancelled" : @"not-exported");
        NSString *detail = reasons.count ? [reasons componentsJoinedByString:@"\n"] :
            (cancelled ? NSLocalizedString(@"No output was committed because the operation was cancelled.", nil) :
                         NSLocalizedString(@"No output was committed because the batch did not complete. The original was preserved.", nil));
        [results addObject:@{@"source": source, @"outcome": outcome, @"detail": detail}];
    }
    return results;
}
