import Foundation

@objc(HorosURLImportDownloadResult)
public final class URLImportDownloadResult: NSObject {
    @objc public let index: Int
    @objc public let url: URL
    @objc public let data: Data?
    @objc public let error: NSError?

    init(index: Int, url: URL, data: Data?, error: NSError?) {
        self.index = index
        self.url = url
        self.data = data
        self.error = error
    }
}

/// Parallel transfers consumed by one background database-owning thread.
@objc(HorosURLImportDownloads)
public final class URLImportDownloads: NSObject {
    private let condition = NSCondition()
    private let urls: [URL]
    private var pending: Set<Int>
    private var ready: [URLImportDownloadResult] = []
    private let session: URLSession
    private let requestTimeout: TimeInterval
    private let totalTimeout: TimeInterval

    @objc(initWithURLs:requestTimeout:totalTimeout:)
    public init(urls: [URL], requestTimeout: TimeInterval, totalTimeout: TimeInterval) {
        self.urls = urls
        self.pending = Set(urls.indices)
        self.requestTimeout = requestTimeout
        self.totalTimeout = totalTimeout
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = requestTimeout
        configuration.timeoutIntervalForResource = totalTimeout
        configuration.httpMaximumConnectionsPerHost = max(1, min(urls.count, 8))
        self.session = URLSession(configuration: configuration)
        super.init()
        for (index, url) in urls.enumerated() {
            if url.isFileURL {
                DispatchQueue.global(qos: .utility).async { [weak self] in
                    do { self?.finish(index: index, data: try Data(contentsOf: url), error: nil) }
                    catch { self?.finish(index: index, data: nil, error: error as NSError) }
                }
            } else {
                session.dataTask(with: url) { [weak self] data, response, error in
                    var failure = error as NSError?
                    if failure == nil, let http = response as? HTTPURLResponse,
                       !(200..<300).contains(http.statusCode) {
                        failure = NSError(domain: NSURLErrorDomain, code: NSURLErrorBadServerResponse,
                            userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
                    }
                    self?.finish(index: index, data: failure == nil ? data : nil, error: failure)
                }.resume()
            }
        }
    }

    private func finish(index: Int, data: Data?, error: NSError?) {
        condition.lock()
        defer { condition.unlock() }
        guard pending.remove(index) != nil else { return }
        var failure = error
        if error?.domain == NSURLErrorDomain && error?.code == NSURLErrorTimedOut {
            failure = NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut,
                userInfo: [NSLocalizedDescriptionKey: "Download timed out (request limit \(Int(requestTimeout)) s; total limit \(Int(totalTimeout)) s)."])
        }
        ready.append(URLImportDownloadResult(index: index, url: urls[index], data: data, error: failure))
        condition.signal()
    }

    /// Bounded wait lets the owning activity observe its cancellation flag.
    @objc public func nextResult() -> URLImportDownloadResult? {
        condition.lock()
        defer { condition.unlock() }
        if ready.isEmpty && !pending.isEmpty {
            _ = condition.wait(until: Date(timeIntervalSinceNow: 0.1))
        }
        return ready.isEmpty ? nil : ready.removeFirst()
    }

    @objc public var finished: Bool {
        condition.lock()
        defer { condition.unlock() }
        return pending.isEmpty && ready.isEmpty
    }

    @objc public func cancel() {
        condition.lock()
        let failure = NSError(domain: NSURLErrorDomain, code: NSURLErrorCancelled,
                              userInfo: [NSLocalizedDescriptionKey: "Download cancelled."])
        ready = ready.map { URLImportDownloadResult(index: $0.index, url: $0.url, data: nil, error: failure) }
        for index in pending.sorted() {
            ready.append(URLImportDownloadResult(index: index, url: urls[index], data: nil, error: failure))
        }
        pending.removeAll()
        condition.broadcast()
        condition.unlock()
        session.invalidateAndCancel()
    }

    deinit { session.invalidateAndCancel() }
}
