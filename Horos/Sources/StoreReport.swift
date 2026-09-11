import Foundation

/// Why each file of a DICOM send did or did not arrive.
///
/// A send that lost files told the user `Errors ! 3 of 40 files generated
/// errors.` and, if they opened the alert, `Unsuccessful Store Encountered, see
/// Applications/Utilities/Console.app for more detailed informations.` The
/// detailed information was `fprintf(stderr, …)`, which a released application
/// has nowhere to put, and it named a file without saying which of three quite
/// different things had gone wrong:
///
/// - the **file** could not be read, or carries no SOP Class and SOP Instance
///   UID, so no C-STORE could name it;
/// - the **negotiation** produced no presentation context the node would accept
///   for that SOP class in that transfer syntax;
/// - the **DIMSE message** was answered with a failure status, or the
///   transmission itself failed.
///
/// The first two are properties of one file; the association is unharmed and the
/// rest of the send can go on. A transmission that failed is not, and going on
/// would only produce more failures.
@objc(HorosStoreReport)
public final class StoreReport: NSObject {
    enum Outcome {
        case sent(statusText: String)
        case unreadable(reason: String)
        case withoutIdentity
        case notStorage(sopClassUID: String)
        case noPresentationContext(sopClassUID: String, transferSyntax: String)
        case rejected(statusText: String)
        case transportFailure(reason: String)

        /// Whether the association survives it, so the remaining files can still
        /// be sent.
        var isFileLevel: Bool {
            switch self {
            case .sent, .transportFailure: return false
            default: return true
            }
        }

        var succeeded: Bool {
            if case .sent = self { return true }
            return false
        }
    }

    private var entries: [(path: String, outcome: Outcome)] = []

    @objc public func reset() {
        entries.removeAll()
    }

    @objc(recordSentPath:statusText:)
    public func recordSent(path: String, statusText: String) {
        entries.append((path, .sent(statusText: statusText)))
    }

    @objc(recordUnreadablePath:reason:)
    public func recordUnreadable(path: String, reason: String) {
        entries.append((path, .unreadable(reason: reason)))
    }

    @objc(recordPathWithoutIdentity:)
    public func recordWithoutIdentity(path: String) {
        entries.append((path, .withoutIdentity))
    }

    @objc(recordNonStoragePath:sopClassUID:)
    public func recordNonStorage(path: String, sopClassUID: String) {
        entries.append((path, .notStorage(sopClassUID: sopClassUID)))
    }

    @objc(recordNoPresentationContextPath:sopClassUID:transferSyntax:)
    public func recordNoPresentationContext(path: String, sopClassUID: String,
                                            transferSyntax: String) {
        entries.append((path, .noPresentationContext(sopClassUID: sopClassUID,
                                                     transferSyntax: transferSyntax)))
    }

    @objc(recordRejectedPath:statusText:)
    public func recordRejected(path: String, statusText: String) {
        entries.append((path, .rejected(statusText: statusText)))
    }

    @objc(recordTransportFailurePath:reason:)
    public func recordTransportFailure(path: String, reason: String) {
        entries.append((path, .transportFailure(reason: reason)))
    }

    /// Whether the last thing that went wrong was about one file rather than
    /// about the association, so the send can carry on with the next file.
    @objc public var lastFailureIsFileLevel: Bool {
        guard let last = entries.last(where: { !$0.outcome.succeeded }) else { return true }
        return last.outcome.isFileLevel
    }

    @objc public var sentCount: Int { return entries.filter { $0.outcome.succeeded }.count }
    @objc public var failedCount: Int { return entries.count - sentCount }
    @objc public var isComplete: Bool { return failedCount == 0 }

    /// The files that did not arrive, in the order they were attempted.
    @objc public var failedPaths: [String] {
        return entries.filter { !$0.outcome.succeeded }.map { $0.path }
    }

    /// One line naming how many failed and of what kind, so a user who reads
    /// only the notification knows where to look.
    @objc public var summary: String {
        if entries.isEmpty {
            return "Nothing was sent."
        }
        if isComplete {
            return "\(sentCount) of \(sentCount) sent."
        }
        var kinds: [String] = []
        func count(_ label: String, _ matching: (Outcome) -> Bool) {
            let n = entries.filter { matching($0.outcome) }.count
            if n > 0 { kinds.append("\(n) \(label)") }
        }
        count("the file could not be read or names no SOP Instance") {
            if case .unreadable = $0 { return true }
            if case .withoutIdentity = $0 { return true }
            if case .notStorage = $0 { return true }
            return false
        }
        count("the node accepted no presentation context") {
            if case .noPresentationContext = $0 { return true }
            return false
        }
        count("the node refused the C-STORE") {
            if case .rejected = $0 { return true }
            return false
        }
        count("the transmission failed") {
            if case .transportFailure = $0 { return true }
            return false
        }
        return "\(sentCount) of \(entries.count) sent; \(failedCount) failed — "
            + kinds.joined(separator: ", ") + "."
    }

    /// A line per file that did not arrive, saying which of the three things
    /// happened. Bounded, because a large send fails largely.
    @objc(detailWithLimit:)
    public func detail(limit: Int) -> String {
        let failed = entries.filter { !$0.outcome.succeeded }
        if failed.isEmpty {
            return summary
        }
        let shown = failed.prefix(max(limit, 0))
        var lines = shown.map { entry in "  " + sentence(for: entry.path, entry.outcome) }
        if failed.count > shown.count {
            lines.append("  … and \(failed.count - shown.count) more")
        }
        return ([summary] + lines).joined(separator: "\n")
    }

    func sentence(for path: String, _ outcome: Outcome) -> String {
        let name = (path as NSString).lastPathComponent
        switch outcome {
        case .sent(let statusText):
            return "\(name): sent, \(statusText)."
        case .unreadable(let reason):
            return "\(name): the file could not be read as DICOM — \(reason)."
        case .withoutIdentity:
            return "\(name): the file has no SOP Class and SOP Instance UID, "
                + "so no C-STORE could name what it holds."
        case .notStorage(let sopClassUID):
            return "\(name): \(sopClassUID) is not a storage SOP class, so it cannot be sent "
                + "with a C-STORE."
        case .noPresentationContext(let sopClassUID, let transferSyntax):
            return "\(name): the node accepted no presentation context for \(sopClassUID) "
                + "in \(transferSyntax). The association is up — a successful C-ECHO says "
                + "nothing about which SOP classes and transfer syntaxes it will take."
        case .rejected(let statusText):
            return "\(name): the node answered the C-STORE with \(statusText)."
        case .transportFailure(let reason):
            return "\(name): the transmission failed — \(reason)."
        }
    }
}
