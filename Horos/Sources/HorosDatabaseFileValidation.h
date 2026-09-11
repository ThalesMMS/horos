// SPDX-License-Identifier: LGPL-3.0-or-later
#import <Foundation/Foundation.h>
#import <CoreData/CoreData.h>
#include <string.h>
#include <sqlite3.h>

// Inspect explicitly opened files before entering database creation or migration.
static inline BOOL HorosIsDatabaseFile(NSString *path)
{
    if (![path.lastPathComponent isEqualToString:@"Database.sql"] ||
        ![path.stringByDeletingLastPathComponent.lastPathComponent isEqualToString:@"Horos Data"])
        return NO;

    NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:NULL];
    if (![attributes.fileType isEqualToString:NSFileTypeRegular]) return NO;
    NSFileHandle *file = [NSFileHandle fileHandleForReadingAtPath:path];
    if (!file) return NO;
    BOOL isSQLite = NO;
    @try {
        NSData *header = [file readDataOfLength:16];
        isSQLite = header.length == 16 && memcmp(header.bytes, "SQLite format 3\0", 16) == 0;
    } @catch (NSException *exception) {
        return NO;
    } @finally {
        [file closeFile];
    }
    if (!isSQLite) return NO;

    // Core Data's metadata API can change an unrelated SQLite store's journal
    // mode even with NSReadOnlyPersistentStoreOption. Inspect the existing
    // metadata directly without letting Core Data open or migrate this file.
    sqlite3 *database = NULL;
    if (sqlite3_open_v2(path.fileSystemRepresentation, &database,
                        SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, NULL) != SQLITE_OK) {
        if (database) sqlite3_close(database);
        return NO;
    }
    sqlite3_stmt *statement = NULL;
    NSData *metadataData = nil;
    if (sqlite3_prepare_v2(database, "SELECT Z_PLIST FROM Z_METADATA LIMIT 1", -1, &statement, NULL) == SQLITE_OK &&
        sqlite3_step(statement) == SQLITE_ROW && sqlite3_column_type(statement, 0) == SQLITE_BLOB) {
        metadataData = [NSData dataWithBytes:sqlite3_column_blob(statement, 0)
                                     length:sqlite3_column_bytes(statement, 0)];
    }
    sqlite3_finalize(statement);
    sqlite3_close(database);
    if (!metadataData) return NO;
    NSDictionary *metadata = [NSPropertyListSerialization propertyListWithData:metadataData
        options:NSPropertyListImmutable format:NULL error:NULL];
    if (![metadata isKindOfClass:NSDictionary.class]) return NO;
    NSDictionary *entities = metadata[NSStoreModelVersionHashesKey];
    if (![entities isKindOfClass:NSDictionary.class]) return NO;
    return entities[@"Study"] && entities[@"Series"] && entities[@"Image"] && entities[@"Album"];
}
