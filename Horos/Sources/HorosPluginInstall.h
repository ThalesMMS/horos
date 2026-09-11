#import <Foundation/Foundation.h>
#import "HorosPluginSignature.h"
#include <stdio.h>
#include <errno.h>

// Stage on the destination volume, then publish the complete directory in one
// filesystem operation. Never delete a working installation before publication.
// After a swap the previous bundle is kept beside the destination so a later
// initialization failure can put it back.
static NSString *HorosPluginPreviousPath(NSString *destination)
{
    return [[destination.stringByDeletingLastPathComponent
             stringByAppendingPathComponent:@".horos-plugin-previous"]
            stringByAppendingPathComponent:destination.lastPathComponent];
}

static BOOL HorosRetainPreviousPlugin(NSString *stagedOld, NSString *destination)
{
    NSFileManager *manager = [NSFileManager defaultManager];
    if (![manager fileExistsAtPath:stagedOld])
        return YES;
    NSString *previous = HorosPluginPreviousPath(destination);
    NSString *parent = previous.stringByDeletingLastPathComponent;
    if (![manager createDirectoryAtPath:parent withIntermediateDirectories:YES attributes:nil error:NULL])
        return NO;
    [manager removeItemAtPath:previous error:NULL];
    return [manager moveItemAtPath:stagedOld toPath:previous error:NULL];
}

static BOOL HorosRestorePreviousPlugin(NSString *destination, NSError **error)
{
    NSFileManager *manager = [NSFileManager defaultManager];
    NSString *previous = HorosPluginPreviousPath(destination);
    if (![manager fileExistsAtPath:previous] || ![manager fileExistsAtPath:destination]) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:ENOENT userInfo:nil];
        return NO;
    }
    if (renamex_np(previous.fileSystemRepresentation, destination.fileSystemRepresentation, RENAME_SWAP) != 0) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
        return NO;
    }
    [manager removeItemAtPath:previous error:NULL];
    NSString *parent = previous.stringByDeletingLastPathComponent;
    if ([manager contentsOfDirectoryAtPath:parent error:NULL].count == 0)
        [manager removeItemAtPath:parent error:NULL];
    return YES;
}

static BOOL HorosInstallPlugin(NSString *source, NSString *destination, NSError **error)
{
    NSFileManager *manager = [NSFileManager defaultManager];
    NSString *parent = destination.stringByDeletingLastPathComponent;
    if (![manager createDirectoryAtPath:parent withIntermediateDirectories:YES attributes:nil error:error])
        return NO;
    NSString *staging = [parent stringByAppendingPathComponent:
        [@".horos-plugin-update-" stringByAppendingString:NSUUID.UUID.UUIDString]];
    if (![manager createDirectoryAtPath:staging withIntermediateDirectories:NO attributes:nil error:error])
        return NO;
    NSString *candidatePath = [staging stringByAppendingPathComponent:destination.lastPathComponent];
    BOOL installed = NO;
    @try {
        if (![manager copyItemAtPath:source toPath:candidatePath error:error])
            return NO;
        NSBundle *candidate = [NSBundle bundleWithPath:candidatePath];
        if (!candidate || ![candidate preflightAndReturnError:error] ||
            !HorosPluginSignatureAllowsLoading(candidatePath, error))
            return NO;

        unsigned int flags = [manager fileExistsAtPath:destination] ? RENAME_SWAP : RENAME_EXCL;
        if (renamex_np(candidatePath.fileSystemRepresentation, destination.fileSystemRepresentation, flags) != 0) {
            if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
            return NO;
        }
        installed = YES;
    }
    @finally {
        // After a swap, the old installation is inside staging until it is
        // moved to the previous path. On failure only the unpublished
        // candidate is there. The source is always retained.
        BOOL kept = !installed || HorosRetainPreviousPlugin(candidatePath, destination);
        if (kept)
            [manager removeItemAtPath:staging error:NULL];
    }
    return installed;
}
