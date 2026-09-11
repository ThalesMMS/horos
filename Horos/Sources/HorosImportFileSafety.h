#import <Foundation/Foundation.h>
#import <CoreData/CoreData.h>
#import "N2ManagedDatabase.h"
#import "HorosReportExtraction.h"

// Preserve rejected input for inspection, without moving indexed or external files.
static inline NSString *HorosQuarantineUnindexedImport(N2ManagedObjectContext *context,
                                                       NSString *source, NSString *dataDirectory,
                                                       NSString *errorsDirectory)
{
    if (!context || context.defersSaves || !source.length || !dataDirectory.length || !errorsDirectory.length)
        return nil;
    NSFileManager *manager = NSFileManager.defaultManager;
    NSDictionary *attributes = [manager attributesOfItemAtPath:source error:NULL];
    if (![attributes.fileType isEqualToString:NSFileTypeRegular]) return nil;
    NSString *canonical = source.stringByStandardizingPath.stringByResolvingSymlinksInPath;
    NSString *root = dataDirectory.stringByStandardizingPath.stringByResolvingSymlinksInPath;
    if (![canonical hasPrefix:[root stringByAppendingString:@"/"]]) return nil;
    NSString *filename = source.lastPathComponent;
    NSMutableArray *predicates = [NSMutableArray arrayWithObject:
        [NSPredicate predicateWithFormat:@"pathString IN %@", @[source, canonical, filename]]];
    int number = [filename.stringByDeletingPathExtension intValue];
    if ([filename isEqualToString:[NSString stringWithFormat:@"%d.dcm", number]])
        [predicates addObject:[NSPredicate predicateWithFormat:@"pathNumber == %@", @(number)]];
    NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"Image"];
    request.predicate = [NSCompoundPredicate orPredicateWithSubpredicates:predicates];
    NSError *error = nil;
    NSUInteger references = [context countForFetchRequest:request error:&error];
    if (error || references != 0) return nil;
    // Pending deletions must not hide references still present in the store.
    request.includesPendingChanges = NO;
    references = [context countForFetchRequest:request error:&error];
    if (error || references != 0) return nil;
    if (![manager createDirectoryAtPath:errorsDirectory withIntermediateDirectories:YES attributes:nil error:NULL])
        return nil;
    NSString *destination = [errorsDirectory stringByAppendingPathComponent:
        [NSString stringWithFormat:@"%@-%@", NSUUID.UUID.UUIDString, filename]];
    return [manager moveItemAtPath:source toPath:destination error:NULL] ? destination : nil;
}

// Never overwrite a report referenced by the durable database during import.
// Keep the extracted report separate until its new URL is saved; rollback owns
// only this newly created file. Older reports may still have other references.
static inline NSString *HorosPrepareImportedReport(N2ManagedObjectContext *context,
                                                   NSString *extractedPath, NSString *reportsDirectory,
                                                   NSError **error)
{
    NSString *filename = [NSString stringWithFormat:@"%@-%@", NSUUID.UUID.UUIDString, extractedPath.lastPathComponent];
    NSString *destination = [reportsDirectory stringByAppendingPathComponent:filename];
    NSFileManager *manager = NSFileManager.defaultManager;
    if (![manager moveItemAtPath:extractedPath toPath:destination error:error]) return nil;
    HorosCleanReportExtractionParent(extractedPath);
    NSDictionary *created = [manager attributesOfItemAtPath:destination error:NULL];
    [context performAfterDiscardingChanges:^{
        NSDictionary *current = [NSFileManager.defaultManager attributesOfItemAtPath:destination error:NULL];
        if ([[current objectForKey:NSFileSystemFileNumber] isEqual:[created objectForKey:NSFileSystemFileNumber]] &&
            [[current objectForKey:NSFileSystemNumber] isEqual:[created objectForKey:NSFileSystemNumber]])
            [NSFileManager.defaultManager removeItemAtPath:destination error:NULL];
    }];
    return [@"REPORTS/" stringByAppendingPathComponent:filename];
}

// Keep the previous bytes until both the replacement and its index are durable.
// A multiframe file may still be referenced by frames outside this import batch.
static inline void HorosRetireImportedFileAfterSave(N2ManagedObjectContext *context,
                                                   NSString *oldPath, NSString *newPath)
{
    if (![context respondsToSelector:@selector(performAfterNextSuccessfulSave:)] ||
        !oldPath.length || !newPath.length || [oldPath isEqualToString:newPath])
        return;
    NSDictionary *originalAttributes = [[NSFileManager defaultManager] attributesOfItemAtPath:oldPath error:NULL];
    if (!originalAttributes) return;
    // The context owns the callback; avoid a retain cycle back to its owner.
    __unsafe_unretained N2ManagedObjectContext *owner = context;
    [context performAfterNextSuccessfulSave:^{
        NSDictionary *replacement = [[NSFileManager defaultManager] attributesOfItemAtPath:newPath error:NULL];
        if (![replacement.fileType isEqualToString:NSFileTypeRegular] || !replacement.fileSize)
            return;
        NSFetchRequest *request = [NSFetchRequest fetchRequestWithEntityName:@"Image"];
        // `path` is a computed accessor, not a persisted Core Data attribute.
        NSString *filename = oldPath.lastPathComponent;
        NSMutableArray *predicates = [NSMutableArray arrayWithObject:
            [NSPredicate predicateWithFormat:@"pathString IN %@", @[oldPath, filename]]];
        int number = [filename.stringByDeletingPathExtension intValue];
        if ([filename isEqualToString:[NSString stringWithFormat:@"%d.dcm", number]])
            [predicates addObject:[NSPredicate predicateWithFormat:@"pathNumber == %@", @(number)]];
        request.predicate = [NSCompoundPredicate orPredicateWithSubpredicates:predicates];
        NSError *error = nil;
        NSUInteger references = [owner countForFetchRequest:request error:&error];
        if (error || references != 0)
            return;
        NSDictionary *current = [[NSFileManager defaultManager] attributesOfItemAtPath:oldPath error:NULL];
        if (![[current objectForKey:NSFileSystemFileNumber] isEqual:[originalAttributes objectForKey:NSFileSystemFileNumber]] ||
            ![[current objectForKey:NSFileSystemNumber] isEqual:[originalAttributes objectForKey:NSFileSystemNumber]])
            return;
        [[NSFileManager defaultManager] removeItemAtPath:oldPath error:NULL];
    }];
}
