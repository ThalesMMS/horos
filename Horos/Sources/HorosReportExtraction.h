#import <Foundation/Foundation.h>
#include "ThirdParty/Libarchive/archive.h"
#include "ThirdParty/Libarchive/archive_entry.h"
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

// A caller moves the returned report, then removes its empty private parent.
static inline void HorosCleanReportExtractionParent(NSString *report)
{
    NSString *parent = report.stringByDeletingLastPathComponent;
    if ([parent.lastPathComponent hasPrefix:@".horos-report-"])
        rmdir(parent.fileSystemRepresentation); // Never recursively remove caller files.
}

static inline NSString *HorosExtractReportArchiveWithLayout(NSData *data, NSDate *date, BOOL packageContents)
{
    if (!data.length) return nil;
    char *pattern = strdup([[NSTemporaryDirectory() stringByAppendingPathComponent:@".horos-report-XXXXXX"] fileSystemRepresentation]);
    if (!pattern) return nil;
    char *created = mkdtemp(pattern);
    NSString *directory = created ? [NSFileManager.defaultManager stringWithFileSystemRepresentation:created length:strlen(created)] : nil;
    free(pattern);
    if (!directory) return nil;
    struct archive *reader = archive_read_new();
    NSString *result = nil;
    BOOL valid = reader != NULL;
    @try {
        if (valid) valid = archive_read_support_format_zip(reader) == ARCHIVE_OK &&
            archive_read_open_memory(reader, data.bytes, data.length) == ARCHIVE_OK;
        struct archive_entry *entry = NULL;
        int status = ARCHIVE_FATAL;
        BOOL hasContent = NO;
        while (valid && (status = archive_read_next_header(reader, &entry)) == ARCHIVE_OK) {
            const char *raw = archive_entry_pathname_utf8(entry);
            NSString *name = raw ? [NSString stringWithUTF8String:raw] : nil;
            while ([name hasPrefix:@"./"]) name = [name substringFromIndex:2];
            if (([name isEqualToString:@"."] || [name isEqualToString:@""]) && archive_entry_filetype(entry) == AE_IFDIR) continue;
            NSArray *parts = [name componentsSeparatedByString:@"/"];
            if (!name.length || name.isAbsolutePath || [parts containsObject:@".."] ||
                [name rangeOfString:@"\\"].location != NSNotFound ||
                [name rangeOfCharacterFromSet:NSCharacterSet.controlCharacterSet].location != NSNotFound ||
                archive_entry_symlink(entry) || archive_entry_hardlink(entry)) { valid = NO; break; }
            mode_t type = archive_entry_filetype(entry);
            if (type != AE_IFREG && type != AE_IFDIR) { valid = NO; break; }
            // Finder ZIP metadata is not a second report and need not be unpacked.
            NSString *top = parts.firstObject;
            if ([top hasPrefix:@"."] || [top isEqualToString:@"__MACOSX"]) {
                valid = archive_read_data_skip(reader) == ARCHIVE_OK;
                continue;
            }
            NSString *path = [directory stringByAppendingPathComponent:name];
            NSFileManager *manager = NSFileManager.defaultManager;
            NSString *parent = type == AE_IFDIR ? path : path.stringByDeletingLastPathComponent;
            if (![manager createDirectoryAtPath:parent withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:NULL]) { valid = NO; break; }
            if (type == AE_IFDIR) continue;
            int fd = open(path.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
            if (fd < 0) { valid = NO; break; }
            char buffer[65536];
            la_ssize_t count;
            while ((count = archive_read_data(reader, buffer, sizeof(buffer))) > 0) {
                hasContent = YES;
                la_ssize_t offset = 0;
                while (offset < count) {
                    ssize_t written = write(fd, buffer + offset, (size_t)(count - offset));
                    if (written < 0 && errno == EINTR) continue;
                    if (written <= 0) { valid = NO; break; }
                    offset += written;
                }
                if (!valid) break;
            }
            if (count < 0) valid = NO;
            if (close(fd) != 0) valid = NO;
        }
        if (status != ARCHIVE_EOF || !hasContent) valid = NO;
        if (valid) {
            NSArray *items = [NSFileManager.defaultManager contentsOfDirectoryAtPath:directory error:NULL];
            if (packageContents) {
                result = directory;
            } else if (items.count == 1) {
                result = [directory stringByAppendingPathComponent:items.firstObject];
                if (date) [NSFileManager.defaultManager setAttributes:@{NSFileModificationDate:date} ofItemAtPath:result error:NULL];
            }
        }
    } @finally {
        if (reader) archive_read_free(reader);
        if (!result) [NSFileManager.defaultManager removeItemAtPath:directory error:NULL];
    }
    return result;
}

// Which kind of Pages document this is, without unpacking it: a template saved
// by Pages '09 keeps its text in index.xml, and one saved by Pages 5 or later
// keeps it in Index/*.iwa, where nothing here can edit it. Unpacking first would
// turn a modern document into a directory, which is not what Pages wrote.
static inline BOOL HorosPagesArchiveHasIndexXML(NSData *data)
{
    if (!data.length) return NO;
    struct archive *reader = archive_read_new();
    if (!reader) return NO;
    BOOL found = NO;
    if (archive_read_support_format_zip(reader) == ARCHIVE_OK &&
        archive_read_open_memory(reader, data.bytes, data.length) == ARCHIVE_OK) {
        struct archive_entry *entry = NULL;
        while (archive_read_next_header(reader, &entry) == ARCHIVE_OK) {
            const char *raw = archive_entry_pathname_utf8(entry);
            NSString *name = raw ? [NSString stringWithUTF8String:raw] : nil;
            while ([name hasPrefix:@"./"]) name = [name substringFromIndex:2];
            if ([name isEqualToString:@"index.xml"]) { found = YES; break; }
            if (archive_read_data_skip(reader) != ARCHIVE_OK) break;
        }
    }
    archive_read_free(reader);
    return found;
}

// SR archives contain one report; Pages ZIP files contain the package's contents.
static inline NSString *HorosExtractReportArchive(NSData *data, NSDate *date)
{
    return HorosExtractReportArchiveWithLayout(data, date, NO);
}

static inline NSString *HorosExtractPagesPackage(NSData *data)
{
    return HorosExtractReportArchiveWithLayout(data, nil, YES);
}
