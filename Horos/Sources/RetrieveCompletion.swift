import Foundation

/// The sub-operation tally a retrieval ends with, and whether it adds up to the
/// study that was asked for.
///
/// A C-MOVE that loses instances does not end in a failure. When the peer cannot
/// send some of its sub-operations it answers `0xB000`, "sub-operations complete,
/// one or more failures", which is a warning; the association is released
/// normally and the requestor is free to read that as an arrival. Measured
/// against a server that failed two of six sub-operations, Horos wrote the
/// counts to `stdout` and told the user nothing: four instances and eleven of
/// twenty-four frames were indexed, and the retrieval reported success.
///
/// So the status alone does not answer the question. The counts do, and this is
/// where they are read and put into words.
@objc(HorosRetrieveCompletion)
public final class RetrieveCompletion: NSObject {

    /// `C-MOVE` or `C-GET` - whichever operation the counts came back from.
    @objc public let operation: String
    /// The DIMSE status of the final response.
    @objc public let status: UInt
    /// What the peer called that status, in its own words, or an empty string.
    @objc public let statusText: String
    @objc public let completed: UInt
    @objc public let failed: UInt
    @objc public let warnings: UInt
    @objc public let remaining: UInt

    @objc public init(operation: String, status: UInt, statusText: String?,
                      completed: UInt, failed: UInt, warnings: UInt, remaining: UInt) {
        self.operation = operation
        self.status = status
        self.statusText = statusText ?? ""
        self.completed = completed
        self.failed = failed
        self.warnings = warnings
        self.remaining = remaining
    }

    /// A timeout preserves the last peer tally, which can lag behind local storage.
    @objc public static func cancellationSummary(operation: String, received: UInt,
                                                  expected: UInt, confirmed: Bool) -> String {
        let tally = expected > 0 ? "\(received) of \(expected) instances" : "\(received) instances (total unknown)"
        let qualification = confirmed ? "received" : "confirmed received in the last response; final count not confirmed"
        return "\(operation) cancelled: \(tally) \(qualification)."
    }

    /// Everything the peer accounted for arrived, and it finished by saying so.
    ///
    /// A sub-operation that ended in a warning did arrive, but something about it
    /// was changed or questioned on the way, so it is not counted as clean here
    /// either: the point of this type is that the user hears about it.
    @objc public var everythingArrived: Bool {
        return status == 0 && failed == 0 && warnings == 0 && remaining == 0
    }

    /// How many sub-operations the peer accounted for, however they ended.
    @objc public var accountedFor: UInt {
        return completed + failed + warnings + remaining
    }

    /// One sentence naming what arrived, what did not, and the status it ended on.
    ///
    /// Written to be read by someone who has just been told a retrieval finished
    /// and needs to know whether the study in front of them is all of it.
    @objc public var summary: String {
        var hexadecimal = String(status, radix: 16)
        while hexadecimal.count < 4 { hexadecimal = "0" + hexadecimal }
        // A peer whose status the network layer cannot name gives back the number
        // it was given, and repeating it adds nothing.
        let named = statusText.isEmpty == false
                 && statusText.lowercased().contains(String(status, radix: 16)) == false
        let ending = named ? "status 0x\(hexadecimal) \(statusText)" : "status 0x\(hexadecimal)"

        if accountedFor == 0 {
            return "\(operation) \(everythingArrived ? "complete" : "failed"): "
                 + "the peer reported no sub-operations (\(ending))"
        }
        if everythingArrived {
            return "\(operation) complete: \(completed) of \(accountedFor) "
                 + "sub-operations arrived (\(ending))"
        }
        return "\(operation) incomplete: \(completed) of \(accountedFor) sub-operations arrived, "
             + "\(failed) failed, \(warnings) with warnings, \(remaining) not attempted (\(ending))"
    }
}
