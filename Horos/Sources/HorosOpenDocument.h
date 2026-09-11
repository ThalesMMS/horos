#import "HorosReportExtraction.h"
#import "HorosReportFileReplacement.h"

// Render a private package and publish only after a complete ZIP has been closed.
static inline BOOL HorosCreateOpenDocument(NSString *templatePath, NSString *destination,
    void (^fill)(NSMutableString *), NSError **error)
{
    return HorosCreateReportFromTemplate(templatePath, destination, ^BOOL(NSString *prepared, NSError **preparationError) {
        NSString *directory = HorosExtractReportArchiveWithLayout([NSData dataWithContentsOfFile:prepared], nil, YES);
        if (!directory) return NO;
        struct archive *writer = NULL;
        @try {
            NSString *contentPath = [directory stringByAppendingPathComponent:@"content.xml"];
            NSString *mime = [NSString stringWithContentsOfFile:[directory stringByAppendingPathComponent:@"mimetype"] encoding:NSUTF8StringEncoding error:NULL];
            if (![mime isEqualToString:@"application/vnd.oasis.opendocument.text"]) return NO;
            NSMutableString *content = [NSMutableString stringWithContentsOfFile:contentPath encoding:NSUTF8StringEncoding error:preparationError];
            if (!content || !fill) return NO;
            NSXMLDocument *xml = [[[NSXMLDocument alloc] initWithXMLString:content options:NSXMLNodeLoadExternalEntitiesNever error:preparationError] autorelease];
            if (!xml || ![xml.rootElement.localName isEqualToString:@"document-content"]) return NO;
            fill(content);
            if (![[[NSXMLDocument alloc] initWithXMLString:content options:NSXMLNodeLoadExternalEntitiesNever error:preparationError] autorelease]) return NO;
            if (![content writeToFile:contentPath atomically:YES encoding:NSUTF8StringEncoding error:preparationError]) return NO;
            NSString *output = [prepared stringByAppendingString:@".new"];
            writer = archive_write_new();
            if (!writer || archive_write_set_format_zip(writer) != ARCHIVE_OK ||
                archive_write_set_options(writer, "zip:compression=store") != ARCHIVE_OK ||
                archive_write_open_filename(writer, output.fileSystemRepresentation) != ARCHIVE_OK) return NO;
            NSMutableArray *names = [NSMutableArray arrayWithObject:@"mimetype"];
            NSArray *remaining = [[NSFileManager.defaultManager subpathsAtPath:directory] sortedArrayUsingSelector:@selector(compare:)];
            for (NSString *name in remaining) if (![name isEqualToString:@"mimetype"]) [names addObject:name];
            for (NSString *name in names) {
                NSString *path = [directory stringByAppendingPathComponent:name];
                NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:preparationError];
                if ([attributes.fileType isEqualToString:NSFileTypeDirectory]) continue;
                if (![attributes.fileType isEqualToString:NSFileTypeRegular]) return NO;
                NSData *data = [NSData dataWithContentsOfFile:path options:0 error:preparationError];
                if (!data) return NO;
                struct archive_entry *entry = archive_entry_new();
                if (!entry) return NO;
                archive_entry_set_pathname(entry, name.UTF8String);
                archive_entry_set_filetype(entry, AE_IFREG);
                archive_entry_set_perm(entry, 0600);
                archive_entry_set_size(entry, data.length);
                int status = archive_write_header(writer, entry);
                archive_entry_free(entry);
                if (status != ARCHIVE_OK) return NO;
                NSUInteger offset = 0;
                while (offset < data.length) {
                    la_ssize_t count = archive_write_data(writer, (const char *)data.bytes + offset, data.length - offset);
                    if (count <= 0) return NO;
                    offset += (NSUInteger)count;
                }
            }
            if (archive_write_close(writer) != ARCHIVE_OK) return NO;
            archive_write_free(writer); writer = NULL;
            return HorosReplaceReportFile(output, prepared, preparationError);
        } @finally {
            if (writer) archive_write_free(writer);
            [NSFileManager.defaultManager removeItemAtPath:directory error:NULL];
        }
    }, error);
}
