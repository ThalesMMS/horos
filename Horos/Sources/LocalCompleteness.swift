import Foundation

/// How much of a remote study or series is already here.
///
/// The query window worked this out in four places, each the same two lines:
/// divide the local file count by the remote one and clamp to 1. That reads a
/// remote total of zero - which is what a node that does not send
/// `NumberOfStudyRelatedInstances` gives you - as **0%**, indistinguishable from
/// a study of which nothing has arrived, and it reads more files locally than the
/// node reports as **100%**, which is the one case where the counts agreeing
/// proves least.
///
/// The three states are kept apart here so that every place that shows this
/// shows the same thing, and so that a column can sort on it.
@objc(HorosLocalCompleteness)
public final class LocalCompleteness: NSObject {
    /// Files of this study or series already in the local database.
    @objc public var inventoryDetail: String?
    @objc public let localCount: Int
    /// What the node said it holds. Meaningless unless `remoteCountIsKnown`.
    @objc public let remoteCount: Int
    /// Whether the node said at all. `NumberOfStudyRelatedInstances` and
    /// `NumberOfSeriesRelatedInstances` are optional, and some nodes omit them.
    @objc public let remoteCountIsKnown: Bool

    @objc(initWithLocalCount:remoteCount:)
    public init(localCount: Int, remoteCount: NSNumber?) {
        self.localCount = max(localCount, 0)
        let remote = remoteCount?.intValue ?? 0
        self.remoteCountIsKnown = remoteCount != nil && remote > 0
        self.remoteCount = max(remote, 0)
        super.init()
    }

    /// The proportion, for a pie chart. Only meaningful when the total is known;
    /// callers should draw nothing at all when it is not, because there is no
    /// proportion to draw.
    @objc public var fraction: Double {
        guard remoteCountIsKnown, remoteCount > 0 else { return 0 }
        return min(Double(localCount) / Double(remoteCount), 1)
    }

    /// Everything the node reports is here - and not more than that.
    ///
    /// This is a statement about counts. Counts can agree while the instances do
    /// not, which is why the retrieval keeps its own manifest; see
    /// `HorosRetrieveManifest`.
    @objc public var isComplete: Bool {
        return remoteCountIsKnown && localCount == remoteCount
    }

    /// More here than the node says it has. Duplicates, a node that undercounts,
    /// or a study that grew - whichever it is, it is not proof of completeness.
    @objc public var exceedsRemote: Bool {
        return remoteCountIsKnown && localCount > remoteCount
    }

    /// What the column shows.
    @objc public var text: String {
        guard remoteCountIsKnown else {
            return localCount > 0 ? "? (\(localCount) local)" : "?"
        }
        let percent = Int((fraction * 100).rounded())
        if exceedsRemote {
            return ">100% (\(localCount)/\(remoteCount))"
        }
        return "\(percent)% (\(localCount)/\(remoteCount))"
    }

    /// What the column sorts on. An unknown total is not a low percentage, so it
    /// sorts apart from one rather than among the empty studies.
    @objc public var sortValue: Double {
        guard remoteCountIsKnown else { return -1 }
        if exceedsRemote { return 1 + Double(localCount - remoteCount) / Double(max(remoteCount, 1)) }
        return fraction
    }

    @objc(compare:)
    public func compare(_ other: LocalCompleteness) -> ComparisonResult {
        if sortValue < other.sortValue { return .orderedAscending }
        if sortValue > other.sortValue { return .orderedDescending }
        return .orderedSame
    }

    /// The sentence under the pointer.
    @objc public var explanation: String {
        if let inventoryDetail { return inventoryDetail }
        guard remoteCountIsKnown else {
            return "\(localCount) here; the node did not say how many it holds."
        }
        if exceedsRemote {
            return "\(localCount) here, more than the \(remoteCount) the node reports."
        }
        if isComplete {
            return "\(localCount) of \(remoteCount) here."
        }
        return "\(localCount) of \(remoteCount) here; \(remoteCount - localCount) still to retrieve."
    }
}
