import Foundation

/// Whether a retrieval needs the DICOM listener to be running.
///
/// A C-MOVE asks the remote node to send the study to a separate application
/// entity, so something has to be listening for it: our own DICOM listener, or
/// an explicit move destination that is somebody else's.
///
/// A WADO retrieval is a C-FIND followed by plain HTTP GETs. Nothing listens for
/// those, and refusing them when the listener is off left a user who runs no SCP
/// unable to retrieve at all.
///
/// C-GET stores sub-operations on its existing association with a request-owned
/// storage context, independently of either plaintext or TLS listeners.
@objc(HorosRetrieveListenerRequirement)
public final class RetrieveListenerRequirement: NSObject {
    // These mirror the enum in DCM Framework/DCMNetServiceDelegate.h.
    static let cMove = 0
    static let cGet = 1
    static let wado = 2
    static let dicomweb = 3

    /// Whether one retrieval, in this mode and with this destination, needs it.
    @objc(listenerRequiredForRetrieveMode:moveDestination:)
    public static func listenerRequired(forRetrieveMode mode: Int,
                                        moveDestination: String?) -> Bool {
        switch mode {
        case wado, dicomweb:
            return false
        case cGet:
            return false
        default:
            // A move destination names some other application entity to receive
            // the study, so our own listener is not the one that has to be up.
            return (moveDestination ?? "").isEmpty
        }
    }

    /// Whether every retrieval in a batch needs it, so a caller can refuse a
    /// batch that cannot produce anything without also refusing the nodes in it
    /// that could have.
    @objc(listenerRequiredForEveryRetrieveMode:)
    public static func listenerRequired(forEveryRetrieveMode modes: [NSNumber]) -> Bool {
        guard !modes.isEmpty else { return false }
        return modes.allSatisfy {
            listenerRequired(forRetrieveMode: $0.intValue, moveDestination: nil)
        }
    }

    /// The retrieve mode of a stored node, with the defaults
    /// `DCMNetServiceDelegate` applies when it normalises one: a missing
    /// `retrieveMode` means C-MOVE unless the legacy `CGET` flag is set.
    @objc(retrieveModeForServer:)
    public static func retrieveMode(forServer server: [String: Any]) -> Int {
        if let stored = server["retrieveMode"] as? NSNumber {
            return stored.intValue
        }
        if let stored = server["retrieveMode"] as? String, !stored.isEmpty {
            return (stored as NSString).integerValue
        }
        if let legacy = server["CGET"] as? NSNumber, legacy.boolValue {
            return cGet
        }
        if let legacy = server["CGET"] as? String, (legacy as NSString).boolValue {
            return cGet
        }
        return cMove
    }

    /// Whether any node the user has configured would need it, so the query
    /// window can warn about the nodes that are actually affected rather than
    /// whenever the listener happens to be off. A missing `Activated` means
    /// activated, again following `DCMNetServiceDelegate`.
    @objc(listenerRequiredForServers:)
    public static func listenerRequired(forServers servers: [[String: Any]]?) -> Bool {
        guard let servers else { return false }
        return servers.contains { server in
            let activated = (server["Activated"] as? NSNumber)?.boolValue
                ?? (server["Activated"] as? String).map { ($0 as NSString).boolValue }
                ?? true
            guard activated else { return false }
            return listenerRequired(forRetrieveMode: retrieveMode(forServer: server),
                                    moveDestination: nil)
        }
    }
}
