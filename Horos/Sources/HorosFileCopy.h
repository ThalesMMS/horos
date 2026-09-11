#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>

static NSError *HorosFileCopyFailure(NSError *underlying, NSString *operation)
{
    NSString *reason = underlying.localizedFailureReason ?: NSLocalizedString(@"Check source availability, destination permissions and free disk space.", nil);
    return [NSError errorWithDomain:underlying.domain ?: @"HorosFileCopy" code:underlying.code
        userInfo:@{NSLocalizedDescriptionKey:[NSString stringWithFormat:@"%@ %@", operation, reason],
                   NSUnderlyingErrorKey:underlying ?: [NSError errorWithDomain:@"HorosFileCopy" code:1 userInfo:nil]}];
}

// Linked when HorosCloudFileAccess is in the process; otherwise a no-op so
// focused copy tests that compile only this header keep their original contract.
static BOOL HorosPrepareCloudCopy(NSString *source, NSString *destination, NSError **error)
{
    Class cls = NSClassFromString(@"HorosCloudFileAccess");
    if (cls == Nil) return YES;
    SEL sel = @selector(prepareCopyFromPath:toPath:error:);
    if (![cls respondsToSelector:sel]) return YES;
    BOOL (*imp)(id, SEL, NSString *, NSString *, NSError **) =
        (BOOL (*)(id, SEL, NSString *, NSString *, NSError **))objc_msgSend;
    return imp(cls, sel, source, destination, error);
}

// Publish only a completed copy. The private staging directory is on the same
// volume as the destination; a failed copy never exposes a partial destination file.
static BOOL HorosCopyFileForPublication(NSFileManager *manager, NSString *source,
                               NSString *destination, BOOL mountedVolume, NSError **error)
{
    if (error) *error = nil;
    if (!HorosPrepareCloudCopy(source, destination, error)) {
        if (error && *error)
            *error = HorosFileCopyFailure(*error, NSLocalizedString(@"The copy could not be completed.", nil));
        return NO;
    }
    NSString *staging = [[destination stringByDeletingLastPathComponent]
        stringByAppendingPathComponent:[@".horos-copy-" stringByAppendingString:NSUUID.UUID.UUIDString]];
    if (![manager createDirectoryAtPath:staging withIntermediateDirectories:NO
        attributes:@{NSFilePosixPermissions:@0700} error:error]) {
        if (error) *error = HorosFileCopyFailure(*error, NSLocalizedString(@"The destination folder could not be prepared.", nil));
        return NO;
    }
    NSString *prepared = [staging stringByAppendingPathComponent:@"payload"];
    @try {
        if (mountedVolume) {
            NSTask *task = [[[NSTask alloc] init] autorelease];
            task.launchPath = @"/bin/cp";
            task.arguments = @[source, prepared];
            task.standardError = [NSFileHandle fileHandleWithNullDevice];
            if (![task launchAndReturnError:error]) return NO;
            [task waitUntilExit];
            if (task.terminationStatus != 0) {
                if (error) *error = [NSError errorWithDomain:@"HorosImportCopy" code:task.terminationStatus
                    userInfo:@{NSLocalizedDescriptionKey:NSLocalizedString(@"The source file could not be copied completely.", nil)}];
                return NO;
            }
        } else if (![manager copyItemAtPath:source toPath:prepared error:error]) return NO;
        // moveItem refuses an existing destination, preserving concurrent data.
        return [manager moveItemAtPath:prepared toPath:destination error:error];
    } @finally {
        if (error && *error) *error = HorosFileCopyFailure(*error, NSLocalizedString(@"The copy could not be completed.", nil));
        [manager removeItemAtPath:staging error:NULL];
    }
}
