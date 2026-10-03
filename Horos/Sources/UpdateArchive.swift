//  Copyright (c) 2026 Thales Matheus M Santos (ThalesMMS)
//
//  This file is part of a fork of Horos (https://github.com/ThalesMMS/horos).
//
//  It is free software: you can redistribute it and/or modify it under the
//  terms of the GNU Lesser General Public License as published by the Free
//  Software Foundation, version 3 of the License.
//
//  It is distributed in the hope that it will be useful, but WITHOUT ANY
//  WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
//  A PARTICULAR PURPOSE. See the GNU Lesser General Public License for details.

#if !MACAPPSTORE
import AppKit
import CryptoKit
import Security

/// Why a downloaded release was not installed. Every case but a failed
/// replacement is decided before the running copy is touched, and a failed
/// replacement puts that copy back.
enum UpdateInstallError: Error, Equatable {
    case cancelled
    case download(String)
    case archiveMismatch
    case extraction
    case wrongApplication
    case unsupportedSystem
    case signature
    case replacement(String)

    var message: String {
        switch self {
        case .cancelled:
            return ""
        case .download(let reason):
            return String(format: NSLocalizedString("The update could not be downloaded: %@", comment: "Update download failure"), reason)
        case .archiveMismatch:
            return NSLocalizedString("The downloaded file does not match the published release.", comment: "Update size or checksum mismatch")
        case .extraction:
            return NSLocalizedString("The downloaded archive could not be opened.", comment: "Update extraction failure")
        case .wrongApplication:
            return NSLocalizedString("The downloaded application is not the published build of Isis DICOM Viewer.", comment: "Update identity mismatch")
        case .unsupportedSystem:
            return NSLocalizedString("The downloaded application requires a newer version of macOS.", comment: "Update system requirement")
        case .signature:
            return NSLocalizedString("The downloaded application is not signed by the developer of this copy, or is not notarized.", comment: "Update signature failure")
        case .replacement(let reason):
            return String(format: NSLocalizedString("Isis DICOM Viewer could not be replaced: %@", comment: "Update replacement failure"), reason)
        }
    }
}

/// Downloads one release archive to a file and accepts it only with the size
/// and SHA-256 its feed gave. Both callbacks run on the main queue; the
/// completion runs once, whatever the outcome.
final class UpdateDownload: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    typealias Progress = @MainActor @Sendable (_ received: Int64, _ expected: Int64) -> Void
    typealias Completion = @MainActor @Sendable (Result<URL, UpdateInstallError>) -> Void

    static var configuration: URLSessionConfiguration {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 3600
        configuration.urlCache = nil
        return configuration
    }

    private let archive: UpdateRelease.Archive
    private let destination: URL
    private let progress: Progress
    private let completion: Completion
    private let lock = NSLock()
    private var session: URLSession?
    private var outcome: Result<URL, UpdateInstallError>?

    init(archive: UpdateRelease.Archive, destination: URL,
         progress: @escaping Progress, completion: @escaping Completion) {
        self.archive = archive
        self.destination = destination
        self.progress = progress
        self.completion = completion
    }

    // Configuration injection keeps the tests independent of the public release.
    func start(configuration: URLSessionConfiguration = UpdateDownload.configuration) {
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        lock.withLock { self.session = session }
        session.downloadTask(with: archive.url).resume()
    }

    func cancel() {
        lock.withLock { session }?.invalidateAndCancel()
    }

    static func sha256(of file: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let block = try handle.read(upToCount: 1 << 20), !block.isEmpty {
            hasher.update(data: block)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private func record(_ result: Result<URL, UpdateInstallError>) {
        lock.withLock { if outcome == nil { outcome = result } }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(request.url?.scheme?.lowercased() == "https" ? request : nil)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didWriteData bytesWritten: Int64, totalBytesWritten: Int64,
                    totalBytesExpectedToWrite: Int64) {
        // A response longer than the published archive is not that archive.
        guard totalBytesWritten <= archive.size else {
            record(.failure(.archiveMismatch))
            downloadTask.cancel()
            return
        }
        let expected = archive.size
        let progress = self.progress
        DispatchQueue.main.async { progress(totalBytesWritten, expected) }
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didFinishDownloadingTo location: URL) {
        guard let response = downloadTask.response as? HTTPURLResponse else {
            record(.failure(.download(NSLocalizedString("The update server returned an invalid response.", comment: "Update check failure"))))
            return
        }
        guard (200...299).contains(response.statusCode) else {
            record(.failure(.download(String(format: NSLocalizedString("The update server returned HTTP %ld. Try again later.", comment: "Update HTTP failure"), response.statusCode))))
            return
        }
        do {
            try FileManager.default.moveItem(at: location, to: destination)
            let size = (try destination.resourceValues(forKeys: [.fileSizeKey]).fileSize).map(Int64.init)
            guard size == archive.size, try Self.sha256(of: destination) == archive.sha256 else {
                try? FileManager.default.removeItem(at: destination)
                record(.failure(.archiveMismatch))
                return
            }
            record(.success(destination))
        } catch {
            record(.failure(.download(error.localizedDescription)))
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        session.finishTasksAndInvalidate()
        let result: Result<URL, UpdateInstallError>
        if let recorded = lock.withLock({ outcome }) {
            result = recorded
        } else if let error = error as NSError? {
            result = .failure(error.domain == NSURLErrorDomain && error.code == NSURLErrorCancelled
                ? .cancelled : .download(error.localizedDescription))
        } else {
            result = .failure(.download(NSLocalizedString("The update server returned an invalid response.", comment: "Update check failure")))
        }
        let completion = self.completion
        DispatchQueue.main.async { completion(result) }
    }
}

/// Where the running copy is, as far as replacing it goes.
enum UpdateLocation: Equatable {
    case replaceable(authorization: Bool)
    case translocated, readOnly, diskImage
}

/// The checks between a downloaded archive and the application that replaces
/// the running copy.
enum UpdateBundle {
    private static func plain(_ text: String) -> Bool {
        !text.isEmpty && text.utf8.allSatisfy {
            (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 46
        }
    }

    /// A Developer ID application of one team, notarized, with one identifier.
    static func requirement(identifier: String, team: String) -> SecRequirement? {
        guard plain(identifier), plain(team) else { return nil }
        let text = "anchor apple generic and identifier \"\(identifier)\""
            + " and certificate 1[field.1.2.840.113635.100.6.2.6] exists"
            + " and certificate leaf[field.1.2.840.113635.100.6.1.13] exists"
            + " and certificate leaf[subject.OU] = \"\(team)\" and notarized"
        var requirement: SecRequirement?
        guard SecRequirementCreateWithString(text as CFString, [], &requirement) == errSecSuccess else { return nil }
        return requirement
    }

    /// The team whose Developer ID signed a notarized copy, which is what a
    /// published release is; nil for a development or re-signed copy. The
    /// copy's resources are not hashed here: this only tells which copies may
    /// be replaced by a download, and the download is validated in full.
    static func developerIDTeam(of bundle: URL) -> String? {
        var code: SecStaticCode?
        var information: CFDictionary?
        guard SecStaticCodeCreateWithPath(bundle as CFURL, [], &code) == errSecSuccess, let code,
              SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &information) == errSecSuccess,
              let values = information as? [String: Any],
              let team = values[kSecCodeInfoTeamIdentifier as String] as? String,
              let identifier = values[kSecCodeInfoIdentifier as String] as? String,
              let requirement = requirement(identifier: identifier, team: team),
              SecStaticCodeCheckValidity(code, SecCSFlags(rawValue: kSecCSDoNotValidateResources), requirement) == errSecSuccess
        else { return nil }
        return team
    }

    /// Extracts the archive into a new folder and returns its one application.
    static func extract(_ archive: URL, into folder: URL) throws -> URL {
        var error: NSError?
        guard HorosRunBoundedTask("/usr/bin/ditto", ["-x", "-k", archive.path, folder.path], 300, &error) != nil else {
            throw UpdateInstallError.extraction
        }
        let keys: [URLResourceKey] = [.isDirectoryKey, .isSymbolicLinkKey]
        let applications = ((try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: keys)) ?? [])
            .filter { $0.pathExtension == "app" }
        guard applications.count == 1, let values = try? applications[0].resourceValues(forKeys: Set(keys)),
              values.isDirectory == true, values.isSymbolicLink != true else {
            throw UpdateInstallError.extraction
        }
        return applications[0]
    }

    /// The extracted application is the build the feed announced, newer than
    /// the installed one, for this system, and signed as the installed copy is.
    static func verify(_ application: URL, release: UpdateRelease, identifier: String,
                       installedBuild: String?, team: String) throws {
        guard let information = NSDictionary(contentsOf: application.appendingPathComponent("Contents/Info.plist")) as? [String: Any],
              information["CFBundleIdentifier"] as? String == identifier,
              information["CFBundleVersion"] as? String == release.build,
              release.isNewer(than: installedBuild) else {
            throw UpdateInstallError.wrongApplication
        }
        if let minimum = (information["LSMinimumSystemVersion"] as? String).flatMap(UpdateRelease.systemVersion),
           !ProcessInfo.processInfo.isOperatingSystemAtLeast(minimum) {
            throw UpdateInstallError.unsupportedSystem
        }
        var code: SecStaticCode?
        let flags = SecCSFlags(rawValue: kSecCSCheckAllArchitectures | kSecCSCheckNestedCode | kSecCSStrictValidate)
        guard let requirement = requirement(identifier: identifier, team: team),
              SecStaticCodeCreateWithPath(application as CFURL, [], &code) == errSecSuccess, let code,
              SecStaticCodeCheckValidity(code, flags, requirement) == errSecSuccess else {
            throw UpdateInstallError.signature
        }
    }

    @MainActor static func location(of bundle: URL) -> UpdateLocation {
        let manager = FileManager.default
        if bundle.pathComponents.contains("AppTranslocation") { return .translocated }
        if (try? bundle.resourceValues(forKeys: [.volumeIsReadOnlyKey]).volumeIsReadOnly) == true { return .readOnly }
        if HorosNativeInstallOperations.containingDiskImage(bundle) != nil { return .diskImage }
        return .replaceable(authorization: !manager.isWritableFile(atPath: bundle.deletingLastPathComponent().path)
            || !manager.isWritableFile(atPath: bundle.path))
    }

    /// Puts `staged` where `destination` is. The previous copy is moved aside
    /// first and put back if the new one cannot take its place; afterwards it
    /// is retired, which in the application means the Trash, from where it can
    /// still be recovered.
    @MainActor static func replace(_ destination: URL, with staged: URL, authorization: Bool,
                                   retire: (URL) throws -> Void = { try FileManager.default.trashItem(at: $0, resultingItemURL: nil) }) throws {
        let manager = FileManager.default
        if (try? destination.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
            throw UpdateInstallError.replacement("The installed application is a symbolic link.")
        }
        let backup = destination.deletingLastPathComponent()
            .appendingPathComponent(".horos-previous-\(UUID().uuidString).app")
        if authorization {
            do {
                try HorosNativeInstallOperations.authorizedShell(HorosNativeInstallOperations.authorizedCommitScript(
                    destination: destination, staging: staged, backup: backup))
            } catch HorosInstallError.cancelled {
                throw UpdateInstallError.cancelled
            } catch {
                throw UpdateInstallError.replacement(error.localizedDescription)
            }
        } else {
            do {
                try manager.moveItem(at: destination, to: backup)
                do {
                    try manager.moveItem(at: staged, to: destination)
                } catch {
                    try? manager.moveItem(at: backup, to: destination)
                    throw error
                }
            } catch {
                throw UpdateInstallError.replacement(error.localizedDescription)
            }
        }
        if manager.fileExists(atPath: backup.path) {
            do { try retire(backup) }
            catch { NSLog("The previous application was retained at %@", backup.path) }
        }
    }
}

#endif
