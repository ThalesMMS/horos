import Foundation

/// Which autorouting rules run now and which wait for their hour.
///
/// `-applyRoutingRules:toImages:` used to walk the rules and, for every
/// activated one, hand `-__applyRoutingRules:` **the whole list**. With two
/// rules every rule was applied twice; with five, five times. A rule carrying a
/// schedule did it again when its delay elapsed — for every other rule too, not
/// just its own.
///
/// The send queue de-duplicates against what is *currently* queued, so the
/// repeats were invisible while the first copy was still there. The routing
/// timer drains that queue every ten seconds, and after it does, the same images
/// are queued again and sent again: an automatic re-send with no new instance
/// behind it.
///
/// Partitioning the rules is the part that was wrong, so it is the part that is
/// here and can be tested.
@objc(HorosRoutingSchedule)
public final class RoutingSchedule: NSObject {
    /// A rule with no `activated` key is activated, as the routing treats it.
    @objc(isActivated:)
    public static func isActivated(_ rule: [String: Any]) -> Bool {
        guard let activated = rule["activated"] else { return true }
        if let number = activated as? NSNumber { return number.boolValue }
        if let text = activated as? String { return text != "0" && !text.isEmpty }
        return true
    }

    /// `0` and a missing key both mean "as soon as the images arrive".
    @objc(scheduleTypeOf:)
    public static func scheduleType(of rule: [String: Any]) -> Int {
        return (rule["scheduleType"] as? NSNumber)?.intValue
            ?? Int(rule["scheduleType"] as? String ?? "") ?? 0
    }

    /// Whether a rule's schedule can actually be worked out. A rule asking for a
    /// time window without the times is not scheduled; it runs now, which is
    /// what the routing already did with it.
    static func isScheduled(_ rule: [String: Any]) -> Bool {
        switch scheduleType(of: rule) {
        case 1:
            return true
        case 2:
            return rule["fromTime"] != nil && rule["toTime"] != nil
        default:
            return false
        }
    }

    /// The rules to apply straight away — as one list, applied once.
    @objc(immediateRulesIn:)
    public static func immediateRules(in rules: [[String: Any]]) -> [[String: Any]] {
        return rules.filter { isActivated($0) && !isScheduled($0) }
    }

    /// The rules that wait. Each is applied by itself when its time comes, so a
    /// schedule on one rule does not re-apply the others.
    @objc(scheduledRulesIn:)
    public static func scheduledRules(in rules: [[String: Any]]) -> [[String: Any]] {
        return rules.filter { isActivated($0) && isScheduled($0) }
    }
}
