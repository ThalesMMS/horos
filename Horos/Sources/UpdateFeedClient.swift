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
import Foundation

/// One stable release as its feed describes it. The archive is present only
/// when the feed names an asset of a release of this fork, with its size and
/// SHA-256: anything else leaves the release known but not downloadable.
@objc(HorosUpdateRelease)
public final class UpdateRelease: NSObject, Sendable {
    public struct Archive: Sendable, Equatable {
        public let url: URL
        public let size: Int64
        public let sha256: String
    }

    @objc public let build: String
    @objc public let version: String?
    public let minimumSystemVersion: OperatingSystemVersion?
    public let archive: Archive?

    /// Assets of this fork's releases; the feed cannot send the download elsewhere.
    static let archivePrefix = "https://github.com/ThalesMMS/horos/releases/download/"
    static let maximumArchiveSize: Int64 = 4 << 30

    init?(feed dictionary: [String: Any]) {
        guard let build = dictionary["Horos"] as? String,
              !build.isEmpty, build.utf8.allSatisfy({ (48...57).contains($0) }),
              let number = Int64(build), number > 0 else { return nil }
        self.build = build
        version = dictionary["Version"] as? String
        minimumSystemVersion = (dictionary["MinimumSystemVersion"] as? String).flatMap(Self.systemVersion)
        if let text = dictionary["ArchiveURL"] as? String, text.hasPrefix(Self.archivePrefix),
           let url = URL(string: text), url.pathExtension == "zip", url.query == nil, url.fragment == nil,
           !url.pathComponents.contains(".."),
           let size = (dictionary["ArchiveSize"] as? NSNumber)?.int64Value, size > 0, size <= Self.maximumArchiveSize,
           let digest = dictionary["ArchiveSHA256"] as? String, digest.utf8.count == 64,
           digest.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }) {
            archive = Archive(url: url, size: size, sha256: digest)
        } else {
            archive = nil
        }
    }

    static func systemVersion(_ text: String) -> OperatingSystemVersion? {
        let parts = text.split(separator: ".", omittingEmptySubsequences: false).map { Int($0) }
        guard (1...3).contains(parts.count), !parts.contains(nil), let major = parts[0], major > 0 else { return nil }
        return OperatingSystemVersion(majorVersion: major, minorVersion: parts.count > 1 ? parts[1]! : 0,
                                      patchVersion: parts.count > 2 ? parts[2]! : 0)
    }

    /// Build numbers are compared as integers; an unreadable installed number counts as older.
    @objc(isNewerThanBuild:)
    public func isNewer(than installed: String?) -> Bool {
        (Int64(build) ?? 0) > (installed.flatMap { Int64($0) } ?? 0)
    }
}

/// Fetches the fork's stable release plist without blocking the UI or weakening TLS.
@objc(HorosUpdateFeedClient)
public final class UpdateFeedClient: NSObject {
    private static let errorDomain = "org.horosproject.update-feed"
    /// The asset of that name in the latest published release that is not a pre-release.
    @objc public static let stableFeedURL = URL(string: "https://github.com/ThalesMMS/horos/releases/latest/download/stable.plist")!
    @objc public static let releasesURL = URL(string: "https://github.com/ThalesMMS/horos/releases")!

    final class HTTPSRedirects: NSObject, URLSessionTaskDelegate {
        func urlSession(_ session: URLSession, task: URLSessionTask,
                        willPerformHTTPRedirection response: HTTPURLResponse,
                        newRequest request: URLRequest,
                        completionHandler: @escaping (URLRequest?) -> Void) {
            completionHandler(request.url?.scheme?.lowercased() == "https" ? request : nil)
        }
    }
    private static let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 20
        configuration.timeoutIntervalForResource = 30
        configuration.urlCache = nil
        return URLSession(configuration: configuration, delegate: HTTPSRedirects(), delegateQueue: nil)
    }()

    private static func failure(_ code: Int, _ text: String) -> NSError {
        NSError(domain: errorDomain, code: code,
                userInfo: [NSLocalizedDescriptionKey: NSLocalizedString(text, comment: "Update check failure")])
    }

    /// `completion` runs once, on the main queue, whatever the outcome.
    @objc(checkURL:completion:)
    public static func check(url: URL, completion: @escaping @MainActor @Sendable (String?, NSError?) -> Void) {
        check(url: url, session: session, completion: completion)
    }

    // Session injection keeps network regression tests independent of the public feed.
    static func check(url: URL, session: URLSession, completion: @escaping @MainActor @Sendable (String?, NSError?) -> Void) {
        fetch(url: url, session: session) { release, error in completion(release?.build, error) }
    }

    /// `completion` runs once, on the main queue, whatever the outcome.
    @objc(fetchURL:completion:)
    public static func fetch(url: URL, completion: @escaping @MainActor @Sendable (UpdateRelease?, NSError?) -> Void) {
        fetch(url: url, session: session, completion: completion)
    }

    static func fetch(url: URL, session: URLSession, completion: @escaping @MainActor @Sendable (UpdateRelease?, NSError?) -> Void) {
        let finish: @Sendable (UpdateRelease?, NSError?) -> Void = { release, error in
            DispatchQueue.main.async { completion(release, error) }
        }
        guard url.scheme?.lowercased() == "https" else {
            finish(nil, failure(1, "The update feed must use HTTPS."))
            return
        }
        session.dataTask(with: url) { data, response, error in
            if let error = error as NSError? {
                finish(nil, error)
                return
            }
            guard let response = response as? HTTPURLResponse else {
                finish(nil, failure(2, "The update server returned an invalid response."))
                return
            }
            guard (200...299).contains(response.statusCode) else {
                finish(nil, NSError(domain: errorDomain, code: 3, userInfo: [
                    NSLocalizedDescriptionKey: String(format: NSLocalizedString("The update server returned HTTP %ld. Try again later.", comment: "Update HTTP failure"), response.statusCode)
                ]))
                return
            }
            guard let data = data, data.count <= 1_048_576,
                  let plist = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil),
                  let dictionary = plist as? [String: Any],
                  let release = UpdateRelease(feed: dictionary) else {
                finish(nil, failure(4, "The update feed is invalid or does not contain a valid Isis DICOM Viewer build number."))
                return
            }
            finish(release, nil)
        }.resume()
    }

    @objc(summaryForInstalledVersion:build:availableBuild:)
    public static func summary(installedVersion: String, build: String, availableBuild: String) -> String {
        String(format: NSLocalizedString("Installed version: %@ (build %@).\nChannel checked: ThalesMMS/horos stable releases.\nBuild reported by that feed: %@.\n\nThis comparison uses build numbers. Development changes and compatibility are not verified; review the release notes before downloading.", comment: "Update result with explicit distribution channel"), installedVersion, build, availableBuild)
    }

    @objc(messageForError:)
    public static func message(for error: NSError) -> String {
        if error.domain == errorDomain { return error.localizedDescription }
        if error.domain == NSURLErrorDomain {
            switch error.code {
            case NSURLErrorServerCertificateHasBadDate, NSURLErrorServerCertificateUntrusted,
                 NSURLErrorServerCertificateHasUnknownRoot, NSURLErrorServerCertificateNotYetValid:
                return NSLocalizedString("The update server's certificate could not be verified. A secure connection is required.", comment: "Update certificate failure")
            case NSURLErrorSecureConnectionFailed, NSURLErrorClientCertificateRejected, NSURLErrorClientCertificateRequired:
                return NSLocalizedString("A secure connection to the update server could not be established.", comment: "Update TLS failure")
            case NSURLErrorNotConnectedToInternet, NSURLErrorNetworkConnectionLost:
                return NSLocalizedString("The network connection is unavailable or was interrupted. Check your connection and try again.", comment: "Update network failure")
            case NSURLErrorTimedOut:
                return NSLocalizedString("The update server did not respond in time. Try again later.", comment: "Update timeout")
            case NSURLErrorCannotFindHost, NSURLErrorCannotConnectToHost, NSURLErrorDNSLookupFailed:
                return NSLocalizedString("The update server could not be reached. Check your connection or try again later.", comment: "Update host failure")
            default: break
            }
        }
        return NSLocalizedString("The update check could not be completed. Try again later.", comment: "Update unknown failure")
    }
}

#endif
