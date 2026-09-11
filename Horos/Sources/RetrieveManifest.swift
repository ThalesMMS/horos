import Foundation

/// What a retrieval asked for and what came back, instance by instance.
///
/// A WADO retrieval knew it was incomplete - `WADODownload` counted successes
/// and logged `errors: 2 / total: 8` - but the counts were numbers, not
/// identities: nothing recorded *which* instances were missing, so nothing could
/// ask for them again, and the alert said the same thing whether one instance
/// was lost or two hundred.
///
/// This is that record. It is keyed by SOP Instance UID, which is what a WADO
/// URL carries in its `objectUID` parameter, so it survives the URL being built
/// again with different parameters.
@objc(HorosRetrieveManifest)
public final class RetrieveManifest: NSObject {
    /// Why an instance is not here.
    ///
    /// The distinction decides whether asking again is worth anything: a
    /// connection that dropped or a server that is busy may well answer next
    /// time, while a 404 means the object is not there to be had.
    enum Failure {
        case transient(String)
        case rejected(String)
    }

    private let order: [String]
    private let urls: [String: URL]
    private var receivedCounts: [String: Int] = [:]
    private var failures: [String: Failure] = [:]
    private let requestedTwice: [String]

    /// The instance a WADO URL asks for. URLs that name none - a plain file
    /// download, say - are their own identity, so the manifest still balances.
    @objc(objectUIDForURL:)
    public static func objectUID(for url: URL) -> String {
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        for item in components?.queryItems ?? [] where item.name.lowercased() == "objectuid" {
            if let value = item.value, !value.isEmpty {
                return value
            }
        }
        return url.absoluteString
    }

    @objc(initWithURLs:)
    public init(urls requested: [URL]) {
        var order: [String] = []
        var byUID: [String: URL] = [:]
        var twice: [String] = []
        for url in requested {
            let uid = RetrieveManifest.objectUID(for: url)
            if byUID[uid] == nil {
                byUID[uid] = url
                order.append(uid)
            } else if !twice.contains(uid) {
                // The same instance asked for under two URLs. The download list
                // is uniqued by URL, which does not catch this.
                twice.append(uid)
            }
        }
        self.order = order
        self.urls = byUID
        self.requestedTwice = twice
        super.init()
    }

    @objc public var requestedCount: Int { return order.count }
    @objc public var receivedCount: Int { return receivedCounts.count }
    @objc public var receivedObjectUIDs: [String] { return order.filter { receivedCounts[$0] != nil } }
    @objc public var isComplete: Bool { return receivedCount == requestedCount }

    /// Asked for once and answered.
    @objc(recordSuccessForURL:)
    public func recordSuccess(forURL url: URL) {
        let uid = RetrieveManifest.objectUID(for: url)
        receivedCounts[uid, default: 0] += 1
        failures[uid] = nil
    }

    /// Asked for and not answered. `statusCode` is the HTTP status, or 0 when
    /// the request never got one.
    @objc(recordFailureForURL:statusCode:reason:)
    public func recordFailure(forURL url: URL, statusCode: Int, reason: String) {
        let uid = RetrieveManifest.objectUID(for: url)
        guard receivedCounts[uid] == nil else { return }
        // 408 request timeout, 425 too early and 429 too many requests are the
        // server asking for a later attempt; so is anything it blames on itself.
        let worthRepeating = statusCode == 0 || statusCode >= 500
            || statusCode == 408 || statusCode == 425 || statusCode == 429
        failures[uid] = worthRepeating ? .transient(reason) : .rejected(reason)
    }

    /// Asked for and neither answered nor refused - the request was cut short.
    @objc(recordAbandonedURL:)
    public func recordAbandoned(url: URL) {
        let uid = RetrieveManifest.objectUID(for: url)
        guard receivedCounts[uid] == nil, failures[uid] == nil else { return }
        failures[uid] = .transient("the retrieval ended before this instance arrived")
    }

    /// Everything asked for that did not arrive, in the order it was asked for.
    @objc public var missingObjectUIDs: [String] {
        return order.filter { receivedCounts[$0] == nil }
    }

    /// Those the server refused outright, which asking again will not fix.
    @objc public var rejectedObjectUIDs: [String] {
        return order.filter {
            if case .rejected = failures[$0] { return true }
            return false
        }
    }

    /// Those that arrived more than once, or were asked for under more than one
    /// URL. A retrieval that reports the right count can still be wrong this
    /// way, which is the case counting files cannot see.
    @objc public var duplicateObjectUIDs: [String] {
        var duplicates = requestedTwice
        for uid in order where (receivedCounts[uid] ?? 0) > 1 && !duplicates.contains(uid) {
            duplicates.append(uid)
        }
        return duplicates
    }

    /// What to ask for again: the missing instances the server has not refused.
    @objc public var retryableURLs: [URL] {
        return order.compactMap { uid in
            guard receivedCounts[uid] == nil else { return nil }
            if case .rejected = failures[uid] { return nil }
            return urls[uid]
        }
    }

    /// Why one instance is not here, for the log.
    @objc(reasonForObjectUID:)
    public func reason(forObjectUID uid: String) -> String? {
        switch failures[uid] {
        case .transient(let reason), .rejected(let reason):
            return reason
        case nil:
            return nil
        }
    }

    /// One line, for a log or an alert: what was asked for, what arrived, and
    /// what did not.
    @objc public var summary: String {
        if isComplete && duplicateObjectUIDs.isEmpty {
            return "\(requestedCount) of \(requestedCount) instances received."
        }
        var parts = ["\(receivedCount) of \(requestedCount) instances received"]
        let rejected = rejectedObjectUIDs.count
        let missing = missingObjectUIDs.count
        if missing > 0 {
            parts.append("\(missing) missing"
                + (rejected > 0 ? " (\(rejected) refused by the server)" : ""))
        }
        if !duplicateObjectUIDs.isEmpty {
            parts.append("\(duplicateObjectUIDs.count) duplicated")
        }
        return parts.joined(separator: ", ") + "."
    }

    /// The missing instances themselves, so a log says which ones rather than
    /// how many. Bounded, because a large study loses a large number.
    @objc(detailWithLimit:)
    public func detail(limit: Int) -> String {
        let missing = missingObjectUIDs
        if missing.isEmpty {
            return summary
        }
        let shown = missing.prefix(max(limit, 0))
        var lines = shown.map { uid -> String in
            "  \(uid): \(reason(forObjectUID: uid) ?? "not received")"
        }
        if missing.count > shown.count {
            lines.append("  … and \(missing.count - shown.count) more")
        }
        return ([summary] + lines).joined(separator: "\n")
    }
}
