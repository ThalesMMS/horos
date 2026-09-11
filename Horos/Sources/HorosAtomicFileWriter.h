#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

// Keep an existing file intact until the writer reports a complete replacement.
static inline BOOL HorosWriteFileAtomically(NSString *destination, BOOL (^writer)(NSString *))
{
    if (!destination.length || !writer) return NO;
    NSFileManager *manager = NSFileManager.defaultManager;
    NSDictionary *existing = [manager attributesOfItemAtPath:destination error:NULL];
    if (existing && ![existing.fileType isEqualToString:NSFileTypeRegular]) return NO;
    NSString *pattern = [destination.stringByDeletingLastPathComponent stringByAppendingPathComponent:@".horos-write-XXXXXX"];
    char *buffer = strdup(pattern.fileSystemRepresentation);
    if (!buffer) return NO;
    BOOL made = mkdtemp(buffer) != NULL;
    NSString *directory = made ? [manager stringWithFileSystemRepresentation:buffer length:strlen(buffer)] : nil;
    free(buffer);
    if (!directory) return NO;
    @try {
        NSString *prepared = [directory stringByAppendingPathComponent:@"complete"];
        if (!writer(prepared)) return NO;
        NSDictionary *attributes = [manager attributesOfItemAtPath:prepared error:NULL];
        if (![attributes.fileType isEqualToString:NSFileTypeRegular] || !attributes.fileSize) return NO;
        if (chmod(prepared.fileSystemRepresentation, 0600) != 0) return NO;
        return rename(prepared.fileSystemRepresentation, destination.fileSystemRepresentation) == 0;
    } @finally {
        [manager removeItemAtPath:directory error:NULL];
    }
}
