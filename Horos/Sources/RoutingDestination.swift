import Foundation

/// Which DICOM node an autorouting rule means.
///
/// A rule stores the destination as the node's `Description` — its display name
/// — and the routing queue looked it up by walking the stored nodes and taking
/// **the first activated one whose name matched**. Three things follow from
/// that, and none of them was reported:
///
/// - Two nodes sharing a name send the study to whichever the list happens to
///   hold first. Reordering the list changes where studies go.
/// - A renamed or deleted node makes the rule match nothing. The files that were
///   already queued for it were dropped with one `N2LogError` line.
/// - A deactivated node is not a match either, so turning a node off silently
///   turns off every rule that names it.
///
/// This resolves the name and says which of those happened, so a rule that
/// cannot say where a study goes does not send it anywhere.
@objc(HorosRoutingDestination)
public final class RoutingDestination: NSObject {
    /// The node, when exactly one activated node has that name.
    @objc public let server: [String: Any]?
    /// What is wrong, in a sentence, when there is no such node. `nil` when the
    /// destination resolved.
    @objc public let problem: String?
    /// Whether asking again could give a different answer. A name that matches
    /// nothing, or matches twice, needs the configuration changed first.
    @objc public let isPermanent: Bool

    init(server: [String: Any]?, problem: String?, isPermanent: Bool) {
        self.server = server
        self.problem = problem
        self.isPermanent = isPermanent
        super.init()
    }

    @objc public var resolved: Bool { return server != nil }

    /// Resolve the destination of a rule against the stored DICOM nodes.
    @objc(destinationNamed:inServers:ruleName:)
    public static func destination(named name: String?,
                                   inServers servers: [[String: Any]],
                                   ruleName: String?) -> RoutingDestination {
        let rule = describe(rule: ruleName)
        guard let name = name, !name.isEmpty else {
            return RoutingDestination(
                server: nil,
                problem: "\(rule) names no destination.",
                isPermanent: true)
        }

        let matching = servers.filter { ($0["Description"] as? String) == name }
        let activated = matching.filter { isActivated($0) }

        if activated.count == 1 {
            return RoutingDestination(server: activated[0], problem: nil, isPermanent: false)
        }
        if activated.count > 1 {
            // Sending to the first would be a guess, and reordering the list
            // would change the answer.
            let where_ = activated.map { address(of: $0) }.joined(separator: ", ")
            return RoutingDestination(
                server: nil,
                problem: "\(rule) is addressed to \"\(name)\", and \(activated.count) DICOM "
                    + "nodes are called that: \(where_). Nothing was sent, because which one "
                    + "is meant cannot be told from the name. Give them different names.",
                isPermanent: true)
        }
        if !matching.isEmpty {
            return RoutingDestination(
                server: nil,
                problem: "\(rule) is addressed to \"\(name)\", which exists but is not "
                    + "activated. Nothing was sent.",
                isPermanent: true)
        }
        return RoutingDestination(
            server: nil,
            problem: "\(rule) is addressed to \"\(name)\", and there is no DICOM node of that "
                + "name. Nothing was sent — a node that was renamed or removed leaves the rules "
                + "that named it pointing at nothing.",
            isPermanent: true)
    }

    /// A node with no `Activated` key is activated, as `DCMNetServiceDelegate`
    /// treats it everywhere else.
    static func isActivated(_ server: [String: Any]) -> Bool {
        guard let activated = server["Activated"] else { return true }
        return (activated as? NSNumber)?.boolValue ?? ((activated as? String).map {
            $0 != "0" && !$0.isEmpty
        } ?? true)
    }

    static func address(of server: [String: Any]) -> String {
        let aet = server["AETitle"] as? String ?? "?"
        let host = server["Address"] as? String ?? "?"
        let port = (server["Port"] as? NSNumber)?.stringValue
            ?? (server["Port"] as? String) ?? "?"
        return "\(aet)@\(host):\(port)"
    }

    static func describe(rule: String?) -> String {
        guard let rule = rule, !rule.isEmpty else { return "A routing rule" }
        return "The routing rule \"\(rule)\""
    }
}

/// The rules whose destination could not be resolved, so the same unanswerable
/// question is not asked — and reported — on every import until the
/// configuration is fixed.
@objc(HorosSuspendedRoutingRules)
public final class SuspendedRoutingRules: NSObject {
    private static let lock = NSLock()
    private static var suspended: [String: String] = [:]

    /// Suspend a rule, and say whether this is the first time. Only the first
    /// time is worth putting in front of anyone.
    @objc(suspendRule:because:)
    @discardableResult
    public static func suspend(rule: String?, because problem: String) -> Bool {
        let key = rule ?? ""
        lock.lock()
        defer { lock.unlock() }
        let isNew = suspended[key] != problem
        suspended[key] = problem
        return isNew
    }

    @objc(problemForRule:)
    public static func problem(forRule rule: String?) -> String? {
        lock.lock()
        defer { lock.unlock() }
        return suspended[rule ?? ""]
    }

    /// Called when the destination resolves again, so a rule fixed in the
    /// preferences starts working without a restart.
    @objc(resumeRule:)
    public static func resume(rule: String?) {
        lock.lock()
        defer { lock.unlock() }
        suspended.removeValue(forKey: rule ?? "")
    }

    @objc public static func resumeAll() {
        lock.lock()
        defer { lock.unlock() }
        suspended.removeAll()
    }

    @objc public static var suspendedRuleNames: [String] {
        lock.lock()
        defer { lock.unlock() }
        return Array(suspended.keys)
    }

    // MARK: - Destinations that are failing

    /// Whether a send failure is worth putting in front of someone.
    ///
    /// A destination that is down fails every batch, and each failure raised a
    /// modal alert on the main thread. A queue of forty batches meant forty
    /// alerts to dismiss before the application could be used again - which is
    /// what "the interface froze while routing" turns out to be. The first
    /// failure of a destination is shown; the repeats are logged and no more.
    @objc(shouldReportProblem:forDestination:)
    public static func shouldReport(problem: String, forDestination destination: String) -> Bool {
        return suspend(rule: "destination:" + destination, because: problem)
    }

    /// The destination answered, so the next failure is news again.
    @objc(clearProblemsForDestination:)
    public static func clearProblems(forDestination destination: String) {
        resume(rule: "destination:" + destination)
    }
}
