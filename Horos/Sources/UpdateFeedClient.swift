import Foundation

/// Fetches the fork's stable build-number plist without blocking the UI or weakening TLS.
@objc(HorosUpdateFeedClient)
public final class UpdateFeedClient: NSObject {
    private static let errorDomain = "org.horosproject.update-feed"
    private final class HTTPSRedirects: NSObject, URLSessionTaskDelegate {
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

    @objc(checkURL:completion:)
    public static func check(url: URL, completion: @escaping (String?, NSError?) -> Void) {
        check(url: url, session: session, completion: completion)
    }

    // Session injection keeps network regression tests independent of the public feed.
    static func check(url: URL, session: URLSession, completion: @escaping (String?, NSError?) -> Void) {
        let finish: (String?, NSError?) -> Void = { version, error in
            DispatchQueue.main.async { completion(version, error) }
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
                  let version = dictionary["Horos"] as? String,
                  !version.isEmpty, version.utf8.allSatisfy({ (48...57).contains($0) }),
                  let number = Int64(version), number > 0 else {
                finish(nil, failure(4, "The update feed is invalid or does not contain a valid Horos build number."))
                return
            }
            finish(version, nil)
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
