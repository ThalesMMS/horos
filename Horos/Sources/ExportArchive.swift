import Foundation
import Darwin

/// Keeps the previous archive in place until a complete replacement is available.
@objc(HorosExportArchive)
public final class ExportArchive: NSObject {
    private let destination: URL
    private let stagingDirectory: URL
    @objc public let archivePath: String

    @objc(initWithDestinationPath:error:)
    public init(destinationPath: String) throws {
        let destination = URL(fileURLWithPath: destinationPath).standardizedFileURL
        let staging = destination.deletingLastPathComponent()
            .appendingPathComponent(".horos-zip-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
        self.destination = destination
        self.stagingDirectory = staging
        self.archivePath = staging.appendingPathComponent("archive.zip").path
        super.init()
    }

    @objc(commitWithError:)
    public func commit() throws {
        // Both paths share a parent filesystem; rename atomically replaces a file.
        // A failed rename leaves the previous destination untouched.
        let failure = archivePath.withCString { source in
            destination.path.withCString { target in
                Darwin.rename(source, target) == 0 ? 0 : errno
            }
        }
        guard failure == 0 else {
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(failure),
                          userInfo: [NSFilePathErrorKey: destination.path])
        }
    }

    deinit {
        try? FileManager.default.removeItem(at: stagingDirectory)
    }
}
