#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

// SR timestamps have coarser precision than filesystem dates. Content identity
// keeps an editor attached to the same file across an archive/import round trip.
static inline BOOL HorosReportsHaveSameContents(NSString *existing, NSString *incoming)
{
    if (!existing.length || !incoming.length) return NO;
    if ([existing hasPrefix:@"http://"] || [existing hasPrefix:@"https://"])
        return [existing isEqualToString:incoming];
    NSFileManager *manager = NSFileManager.defaultManager;
    NSString *leftType = [manager attributesOfItemAtPath:existing error:NULL].fileType;
    NSString *rightType = [manager attributesOfItemAtPath:incoming error:NULL].fileType;
    if (![leftType isEqualToString:rightType] ||
        (![leftType isEqualToString:NSFileTypeRegular] && ![leftType isEqualToString:NSFileTypeDirectory])) return NO;
    return [manager contentsEqualAtPath:existing andPath:incoming];
}

// Prepare on the destination volume, then exchange names in one filesystem
// operation. This also supports nonempty document packages such as .pages.
static inline BOOL HorosReplaceReportFile(NSString *source, NSString *destination, NSError **error)
{
    NSFileManager *manager = NSFileManager.defaultManager;
    if (!source.length || !destination.length) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:EINVAL userInfo:nil];
        return NO;
    }
    NSString *pattern = [destination.stringByDeletingLastPathComponent stringByAppendingPathComponent:@".horos-report-replacement-XXXXXX"];
    char *buffer = strdup(pattern.fileSystemRepresentation);
    if (!buffer) return NO;
    char *created = mkdtemp(buffer);
    NSString *directory = created ? [manager stringWithFileSystemRepresentation:created length:strlen(created)] : nil;
    int creationError = errno;
    free(buffer);
    if (!directory) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:creationError userInfo:nil];
        return NO;
    }
    @try {
        NSString *prepared = [directory stringByAppendingPathComponent:@"report"];
        if (![manager copyItemAtPath:source toPath:prepared error:error]) return NO;
        NSDictionary *existing = [manager attributesOfItemAtPath:destination error:NULL];
        NSDictionary *replacement = [manager attributesOfItemAtPath:prepared error:NULL];
        // Plain files can use portable atomic rename even on volumes without swap.
        if ([existing.fileType isEqualToString:NSFileTypeRegular] &&
            [replacement.fileType isEqualToString:NSFileTypeRegular]) {
            if (rename(prepared.fileSystemRepresentation, destination.fileSystemRepresentation) == 0) return YES;
            if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
            return NO;
        }
        if (@available(macOS 10.12, *)) {
            BOOL exists = existing != nil;
            if (renamex_np(prepared.fileSystemRepresentation, destination.fileSystemRepresentation,
                           exists ? RENAME_SWAP : RENAME_EXCL) == 0) return YES;
            if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
        } else if (error) {
            *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:ENOTSUP userInfo:nil];
        }
        return NO;
    } @finally {
        [manager removeItemAtPath:directory error:NULL];
    }
}

// Render only a private copy; publish after every preparation step succeeds.
static inline BOOL HorosCreateReportFromTemplate(NSString *templatePath, NSString *destination,
    BOOL (^prepare)(NSString *, NSError **), NSError **error)
{
    NSFileManager *manager = NSFileManager.defaultManager;
    if (!templatePath.length || !destination.length || !prepare ||
        [[templatePath stringByResolvingSymlinksInPath] isEqualToString:[destination stringByResolvingSymlinksInPath]]) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:EINVAL userInfo:nil];
        return NO;
    }
    NSString *pattern = [NSTemporaryDirectory() stringByAppendingPathComponent:@"horos-report-template-XXXXXX"];
    char *buffer = strdup(pattern.fileSystemRepresentation);
    if (!buffer) return NO;
    BOOL made = mkdtemp(buffer) != NULL;
    int creationError = errno;
    NSString *directory = made ? [manager stringWithFileSystemRepresentation:buffer length:strlen(buffer)] : nil;
    free(buffer);
    if (!directory) {
        if (error) *error = [NSError errorWithDomain:NSPOSIXErrorDomain code:creationError userInfo:nil];
        return NO;
    }
    @try {
        NSString *name = templatePath.pathExtension.length ? [@"report" stringByAppendingPathExtension:templatePath.pathExtension] : @"report";
        NSString *prepared = [directory stringByAppendingPathComponent:name];
        if (![manager copyItemAtPath:templatePath toPath:prepared error:error]) return NO;
        if (!prepare(prepared, error)) return NO;
        return HorosReplaceReportFile(prepared, destination, error);
    } @catch (NSException *exception) {
        if (error) *error = [NSError errorWithDomain:@"HorosReportPreparation" code:1
            userInfo:@{NSLocalizedDescriptionKey: @"Report preparation failed."}];
        return NO;
    } @finally {
        [manager removeItemAtPath:directory error:NULL];
    }
}
