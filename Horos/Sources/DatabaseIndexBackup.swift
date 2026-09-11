import Foundation
import SQLite3

/// Creates a standalone SQLite recovery snapshot, including committed WAL data.
/// Does not rename/remove the active index or overwrite an earlier backup.
@objc(HorosDatabaseIndexBackup)
public final class DatabaseIndexBackup: NSObject {
    @objc(snapshotAtPath:metadataPath:error:)
    public static func snapshot(atPath path: String, metadataPath: String?) throws -> String {
        let manager = FileManager.default
        let sourceURL = URL(fileURLWithPath: path)
        let folder = sourceURL.deletingLastPathComponent()
            .appendingPathComponent("Index Backups", isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try manager.createDirectory(at: folder, withIntermediateDirectories: true,
                                    attributes: [.posixPermissions: 0o700])
        var complete = false
        defer { if !complete { try? manager.removeItem(at: folder) } }

        var source: OpaquePointer?
        var destination: OpaquePointer?
        defer {
            if let destination { sqlite3_close(destination) }
            if let source { sqlite3_close(source) }
        }
        func failure(_ operation: String, _ database: OpaquePointer?, code: Int32? = nil) -> NSError {
            let result = code ?? sqlite3_errcode(database)
            let detail = code.map { String(cString: sqlite3_errstr($0)) }
                ?? database.map { String(cString: sqlite3_errmsg($0)) } ?? "SQLite connection unavailable"
            return NSError(domain: "HorosDatabaseIndexBackup", code: Int(result),
                           userInfo: [NSLocalizedDescriptionKey: "\(operation): \(detail)"])
        }
        guard sqlite3_open_v2(path, &source, SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, nil) == SQLITE_OK else {
            throw failure("Cannot read the database index", source)
        }
        let output = folder.appendingPathComponent(sourceURL.lastPathComponent)
        guard sqlite3_open_v2(output.path, &destination, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nil) == SQLITE_OK else {
            throw failure("Cannot create the recovery snapshot", destination)
        }
        guard let backup = sqlite3_backup_init(destination, "main", source, "main") else {
            throw failure("Cannot initialize the recovery snapshot", destination)
        }
        let deadline = ProcessInfo.processInfo.systemUptime + 5
        var result: Int32
        repeat {
            result = sqlite3_backup_step(backup, -1)
            if result == SQLITE_BUSY || result == SQLITE_LOCKED {
                Thread.sleep(forTimeInterval: 0.05)
            }
        } while (result == SQLITE_BUSY || result == SQLITE_LOCKED) && ProcessInfo.processInfo.systemUptime < deadline
        let finish = sqlite3_backup_finish(backup)
        guard result == SQLITE_DONE && finish == SQLITE_OK else {
            throw failure("Cannot complete the recovery snapshot", destination,
                          code: result == SQLITE_DONE ? finish : result)
        }
        // Keep the recovery copy self-contained even when the live index uses WAL.
        guard sqlite3_exec(destination, "PRAGMA journal_mode=DELETE", nil, nil, nil) == SQLITE_OK else {
            throw failure("Cannot finalize the recovery snapshot journal", destination)
        }
        var check: OpaquePointer?
        guard sqlite3_prepare_v2(destination, "PRAGMA quick_check", -1, &check, nil) == SQLITE_OK else {
            throw failure("Cannot verify the recovery snapshot", destination)
        }
        defer { sqlite3_finalize(check) }
        guard sqlite3_step(check) == SQLITE_ROW,
              let value = sqlite3_column_text(check, 0), String(cString: value) == "ok" else {
            throw NSError(domain: "HorosDatabaseIndexBackup", code: Int(SQLITE_CORRUPT),
                          userInfo: [NSLocalizedDescriptionKey: "The database recovery snapshot failed its integrity check."])
        }
        if let metadataPath {
            try manager.copyItem(atPath: metadataPath,
                                 toPath: folder.appendingPathComponent(URL(fileURLWithPath: metadataPath).lastPathComponent).path)
        }
        complete = true
        return folder.path
    }
}
