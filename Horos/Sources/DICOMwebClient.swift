import Foundation

private final class DICOMwebAuthorization: @unchecked Sendable {
    let finished = DispatchSemaphore(value: 0)
    var value: Result<String, Error>?
}

private final class DICOMwebResponse: @unchecked Sendable {
    let lock = NSLock()
    let finished = DispatchSemaphore(value: 0)
    var file: URL?
    var response: HTTPURLResponse?
    var error: Error?
    deinit { if let file = file { try? FileManager.default.removeItem(at: file) } }
}

private final class DICOMwebRedirectPolicy: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        // Node URLs are explicit. Never forward an Authorization header through redirects.
        completionHandler(nil)
    }
}

@objc(HorosDICOMwebClient)
public final class DICOMwebClient: NSObject {
    private let endpoint: URL
    private let credentialIdentifier: String
    private let timeout: TimeInterval

    static func failure(_ code: Int, _ message: String) -> NSError {
        NSError(domain: "HorosDICOMweb", code: code, userInfo: [NSLocalizedDescriptionKey: message])
    }

    @objc(initWithEndpoint:credentialIdentifier:timeout:error:)
    public init(endpoint: String, credentialIdentifier: String, timeout: TimeInterval) throws {
        guard let components = URLComponents(string: endpoint), let url = components.url,
              let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil,
              components.scheme == "https" || (components.scheme == "http" && ["localhost", "127.0.0.1", "::1", "[::1]"].contains(host.lowercased()))
        else { throw Self.failure(1, "Enter an HTTPS DICOMweb URL. HTTP is supported only for local testing.") }
        self.endpoint = url
        self.credentialIdentifier = credentialIdentifier
        self.timeout = timeout.isFinite ? min(max(timeout, 1), 3600) : 60
        super.init()
    }

    // Keep cancellation responsive even if the keychain service stops responding.
    // No authorization value is cached or included in diagnostics.
    func authorization(cancelled: () -> Bool, read: @escaping () throws -> String) throws -> String {
        if cancelled() { throw Self.failure(NSURLErrorCancelled, "DICOMweb operation cancelled.") }
        let result = DICOMwebAuthorization()
        DispatchQueue.global(qos: .userInitiated).async {
            result.value = Result { try read() }
            result.finished.signal()
        }
        let deadline = DispatchTime.now() + timeout
        while result.finished.wait(timeout: .now() + 0.1) == .timedOut {
            if cancelled() { throw Self.failure(NSURLErrorCancelled, "DICOMweb operation cancelled.") }
            if DispatchTime.now() >= deadline {
                throw Self.failure(NSURLErrorTimedOut, "DICOMweb credential access timed out. Check the keychain and retry.")
            }
        }
        if cancelled() { throw Self.failure(NSURLErrorCancelled, "DICOMweb operation cancelled.") }
        return try result.value!.get()
    }

    private func request(path: String, parameters: [String: String], accept: String,
                         cancelled: () -> Bool) throws -> (URL, HTTPURLResponse) {
        guard !Thread.isMainThread else { throw Self.failure(2, "DICOMweb operations must run in the background.") }
        var url = endpoint
        for component in path.split(separator: "/") {
            guard component != ".", component != ".." else { throw Self.failure(1, "Invalid DICOMweb resource path.") }
            url.appendPathComponent(String(component))
        }
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        components.queryItems = parameters.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        var request = URLRequest(url: components.url!)
        request.setValue(accept, forHTTPHeaderField: "Accept")
        if !credentialIdentifier.isEmpty {
            let identifier = credentialIdentifier
            let header = try authorization(cancelled: cancelled) { try DICOMwebCredentials.header(identifier: identifier) }
            request.setValue(header, forHTTPHeaderField: "Authorization")
        }
        if cancelled() { throw Self.failure(NSURLErrorCancelled, "DICOMweb operation cancelled.") }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil; configuration.urlCredentialStorage = nil
        configuration.httpCookieStorage = nil; configuration.httpShouldSetCookies = false
        configuration.timeoutIntervalForRequest = timeout
        configuration.timeoutIntervalForResource = timeout
        let session = URLSession(configuration: configuration, delegate: DICOMwebRedirectPolicy(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        let result = DICOMwebResponse()
        let task = session.downloadTask(with: request) { location, response, error in
            result.lock.lock()
            result.error = error
            result.response = response as? HTTPURLResponse
            if let location = location, error == nil {
                let owned = FileManager.default.temporaryDirectory.appendingPathComponent("horos-dicomweb-" + UUID().uuidString)
                do { try FileManager.default.moveItem(at: location, to: owned); result.file = owned }
                catch { result.error = error }
            }
            result.lock.unlock()
            result.finished.signal()
        }
        task.resume()
        let deadline = Date().addingTimeInterval(timeout + 5)
        while result.finished.wait(timeout: .now() + 0.1) == .timedOut {
            if cancelled() { task.cancel(); throw Self.failure(NSURLErrorCancelled, "DICOMweb operation cancelled.") }
            if Date() >= deadline { task.cancel(); throw Self.failure(NSURLErrorTimedOut, "DICOMweb request timed out. Retry or check the node connection.") }
        }
        if cancelled() { throw Self.failure(NSURLErrorCancelled, "DICOMweb operation cancelled.") }
        result.lock.lock(); defer { result.lock.unlock() }
        if let error = result.error as NSError? {
            if error.domain == NSURLErrorDomain && error.code == NSURLErrorTimedOut {
                throw Self.failure(NSURLErrorTimedOut, "DICOMweb request timed out. Retry or check the node connection.")
            }
            throw Self.failure(3, "DICOMweb connection failed. Check the node address, TLS certificate and network.")
        }
        guard let response = result.response else { throw Self.failure(3, "No HTTP response from the DICOMweb node.") }
        if response.statusCode == 401 || response.statusCode == 403 {
            throw Self.failure(response.statusCode, "DICOMweb authentication was rejected or expired. Update the credentials in Locations.")
        }
        guard response.statusCode == 200 || response.statusCode == 204 else {
            throw Self.failure(response.statusCode, "DICOMweb returned HTTP \(response.statusCode). No objects were imported.")
        }
        guard let file = result.file else { throw Self.failure(4, "DICOMweb returned no response body.") }
        result.file = nil
        return (file, response)
    }

    @objc(verifyWithError:)
    public func verify() throws {
        let thread = Thread.current
        let (file, response) = try request(path: "studies", parameters: ["limit": "1"], accept: "application/dicom+json", cancelled: { thread.isCancelled })
        defer { try? FileManager.default.removeItem(at: file) }
        guard response.statusCode == 204 || response.mimeType?.lowercased() == "application/dicom+json" else {
            throw Self.failure(4, "The endpoint did not return a QIDO response.")
        }
    }

    @objc(queryPath:parameters:error:)
    public func query(path: String, parameters: [String: String]) throws -> [[String: Any]] {
        let thread = Thread.current
        return try query(path: path, parameters: parameters, cancelled: { thread.isCancelled })
    }

    func query(path: String, parameters: [String: String], cancelled: () -> Bool) throws -> [[String: Any]] {
        var collected: [[String: Any]] = []
        var seenPages = Set<String>()
        while true {
            var pageParameters = parameters
            pageParameters["limit"] = "100"
            pageParameters["offset"] = String(collected.count)
            let (file, response) = try request(path: path, parameters: pageParameters, accept: "application/dicom+json", cancelled: cancelled)
            defer { try? FileManager.default.removeItem(at: file) }
            if response.statusCode == 204 { return collected }
            guard response.mimeType?.lowercased() == "application/dicom+json",
                  (try file.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max) <= 32 * 1024 * 1024
            else { throw Self.failure(4, "Invalid or oversized QIDO response.") }
            let records: [[String: Any]]
            do {
                let data = try Data(contentsOf: file)
                guard let values = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { throw Self.failure(4, "Invalid QIDO response.") }
                records = values
            } catch { throw Self.failure(4, "The node returned invalid DICOM JSON.") }
            if records.isEmpty { return collected }
            let identities = records.map { record -> String in
                for tag in ["00080018", "0020000E", "0020000D"] {
                    if let attribute = record[tag] as? [String: Any], let values = attribute["Value"] as? [String], let uid = values.first { return uid }
                }
                return ""
            }
            guard !identities.contains(""), seenPages.insert(identities.joined(separator: "|")).inserted,
                  collected.count + records.count <= 10000 else {
                throw Self.failure(4, "QIDO pagination is incomplete or exceeds 10000 results. Narrow the query or check the node.")
            }
            collected.append(contentsOf: records)
            let warning = response.value(forHTTPHeaderField: "Warning") ?? ""
            if records.count < 100 && !warning.contains("299") { return collected }
        }
    }

    @objc(retrievePath:stagingDirectory:error:)
    public func retrieve(path: String, stagingDirectory: String) throws -> [String] {
        let thread = Thread.current
        return try retrieve(path: path, stagingDirectory: stagingDirectory, cancelled: { thread.isCancelled })
    }

    func retrieve(path: String, stagingDirectory: String, cancelled: () -> Bool) throws -> [String] {
        let (file, response) = try request(path: path, parameters: [:],
            accept: "multipart/related; type=\"application/dicom\"; transfer-syntax=*", cancelled: cancelled)
        defer { try? FileManager.default.removeItem(at: file) }
        guard response.statusCode == 200 else { throw Self.failure(4, "The node returned no DICOM objects.") }
        do {
            return try DICOMwebMultipart.extract(from: file, contentType: response.value(forHTTPHeaderField: "Content-Type") ?? "",
                into: URL(fileURLWithPath: stagingDirectory), cancelled: cancelled).map { $0.path }
        } catch DICOMwebMultipart.Failure.cancelled {
            throw Self.failure(NSURLErrorCancelled, "DICOMweb operation cancelled.")
        } catch { throw Self.failure(4, "Incomplete or invalid WADO-RS response. No objects were imported.") }
    }
}
