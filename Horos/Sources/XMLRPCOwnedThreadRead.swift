import CoreData
import Foundation

/// Reads AppKit windows and main-context Core Data on the thread that owns
/// them, then hands the answer back to the XML-RPC connection thread.
///
/// The interface answers on the socket thread. `GetDisplayed2DViewerSeries`
/// used to call `+[ViewerController getDisplayed2DViewers]` there, which asks
/// `[[w window] isKindOfClass:]` and `[w windowWillClose]`, and then
/// `dictionaryForObject:` walked every attribute - `thumbnail` included - on
/// the main-thread context. The hop is here, not inside
/// `getDisplayed2DViewers`: the 2D UI already runs on main.
@objc(HorosXMLRPCOwnedThreadRead)
public final class XMLRPCOwnedThreadRead: NSObject {
    private final class Box: NSObject {
        let work: () -> Any
        var result: Any = NSNull()
        init(_ work: @escaping () -> Any) { self.work = work }
        @objc func run() { result = work() }
    }

    /// Runs `work` on the main thread and waits. Already there: runs in place,
    /// so a caller that is already on main does not deadlock. The connection
    /// thread keeps the result and replies itself.
    @objc(onMainAndWait:)
    public static func onMainAndWait(_ work: @escaping @convention(block) () -> Any) -> Any {
        if Thread.isMainThread { return work() }
        let box = Box(work)
        box.perform(#selector(Box.run), on: Thread.main, with: nil as Any?, waitUntilDone: true)
        return box.result
    }

    /// Attributes a caller may put in an XML-RPC struct: strings, numbers and
    /// dates. Binary ones - the series thumbnail among them - are left unread.
    /// Reading `thumbnail` is what used to lock the main context from a
    /// connection thread and generate an `NSImage` off main.
    @objc(dictionaryForObject:)
    public static func dictionary(for object: NSManagedObject) -> [String: String] {
        var result: [String: String] = [:]
        for (key, description) in object.entity.attributesByName {
            guard isScalar(description.attributeType) else { continue }
            guard let value = object.value(forKey: key) else { continue }
            if value is NSString || value is NSNumber || value is Date {
                result[key] = escaped("\(value)")
            }
        }
        return result
    }

    static func isScalar(_ type: NSAttributeType) -> Bool {
        switch type {
        case .stringAttributeType, .integer16AttributeType, .integer32AttributeType,
             .integer64AttributeType, .decimalAttributeType, .doubleAttributeType,
             .floatAttributeType, .booleanAttributeType, .dateAttributeType:
            return true
        default:
            return false
        }
    }

    static func escaped(_ text: String) -> String {
        var escaped = ""
        escaped.reserveCapacity(text.count)
        for character in text {
            switch character {
            case "&": escaped += "&amp;"
            case "<": escaped += "&lt;"
            case ">": escaped += "&gt;"
            case "'": escaped += "&apos;"
            case "\"": escaped += "&quot;"
            default: escaped.append(character)
            }
        }
        return escaped
    }
}
