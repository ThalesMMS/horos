import Foundation
import Security

/// What to do with an XML-RPC request before any method is dispatched.
@objc(HorosXMLRPCAccessDecision)
public enum XMLRPCAccessDecision: Int {
    /// Dispatch the request.
    case allow
    /// Answer `401` with a `WWW-Authenticate` challenge: the interface wants a
    /// credential and the request either carried none or carried a wrong one.
    case challenge
    /// Answer `403` and dispatch nothing: this peer is not served at all.
    case refuse
}

/// Who the XML-RPC interface answers, and on which interfaces it listens.
///
/// The interface publishes `KillOsiriX`, `Retrieve`, `DownloadURL` and
/// `dbwindowfind` - the last one returns the contents of the database, patient
/// names and identifiers included. It used to bind `INADDR_ANY` and ask for no
/// credential at all, so turning the preference on for a local script published
/// the database to every host that could reach the machine.
///
/// The policy here is deliberately one the user can state in a sentence:
///
/// - By default the socket is bound to loopback. Nothing outside the machine
///   can reach it, and local callers keep working unchanged.
/// - Serving other interfaces is an explicit choice (`httpXMLRPCServerAllowRemote`)
///   and it only takes effect once a credential exists. Without one the listener
///   stays on loopback rather than opening an unauthenticated port.
/// - While it serves other interfaces every request is authenticated, loopback
///   included, so there is a single rule to reason about rather than one per
///   peer.
@objc(HorosXMLRPCServerAccess)
public final class XMLRPCServerAccess: NSObject {
    /// The preference that lets the interface leave loopback.
    @objc public static let allowRemoteKey = "httpXMLRPCServerAllowRemote"

    /// The realm quoted in the challenge, and the account the credential is
    /// stored under.
    @objc public static let realm = "Horos XML-RPC"

    /// Whether the listening socket may be bound to anything but loopback.
    ///
    /// A credential is a precondition, not a separate setting to forget: the
    /// preference alone never opens the port.
    @objc(bindsBeyondLoopbackAllowRemote:hasCredential:)
    public static func bindsBeyondLoopback(allowRemote: Bool, hasCredential: Bool) -> Bool {
        return allowRemote && hasCredential
    }

    /// Whether an accepted peer is the machine itself.
    ///
    /// `N2ConnectionListener` reports the peer as the textual form of its
    /// address, so this reads the same forms `inet_ntop` writes, including the
    /// IPv4-mapped IPv6 addresses a dual-stack accept produces.
    @objc(isLoopbackAddress:)
    public static func isLoopbackAddress(_ address: String?) -> Bool {
        guard var address = address, !address.isEmpty else { return false }
        if let percent = address.firstIndex(of: "%") {
            address = String(address[address.startIndex..<percent])
        }
        if address == "::1" || address == "0:0:0:0:0:0:0:1" { return true }
        for prefix in ["::ffff:", "::FFFF:", "::"] where address.hasPrefix(prefix) {
            let mapped = String(address.dropFirst(prefix.count))
            if mapped.contains(".") { return isLoopbackIPv4(mapped) }
        }
        return isLoopbackIPv4(address)
    }

    /// The whole `127.0.0.0/8` block, not just `127.0.0.1`.
    static func isLoopbackIPv4(_ address: String) -> Bool {
        let parts = address.split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 4 else { return false }
        for part in parts {
            guard !part.isEmpty, part.count <= 3, let value = UInt(part), value <= 255 else { return false }
        }
        return parts[0] == "127"
    }

    /// The verdict on one request, reached before the body is parsed and before
    /// any method runs.
    ///
    /// `credential` is the expected `Authorization` header value, as stored by
    /// `XMLRPCServerCredential`; `authorization` is the one the request carried.
    @objc(decisionForPeerAddress:authorization:credential:listensBeyondLoopback:)
    public static func decision(peerAddress: String?,
                                authorization: String?,
                                credential: String?,
                                listensBeyondLoopback: Bool) -> XMLRPCAccessDecision {
        guard listensBeyondLoopback else {
            // The socket is bound to loopback, so this is a second reading of
            // the same rule rather than the only one enforcing it.
            return isLoopbackAddress(peerAddress) ? .allow : .refuse
        }
        guard let credential = credential, !credential.isEmpty else { return .refuse }
        guard let authorization = authorization, !authorization.isEmpty else { return .challenge }
        return matches(authorization, credential) ? .allow : .challenge
    }

    /// The value of the `WWW-Authenticate` header sent with a `401`.
    @objc public static var challengeHeaderValue: String {
        return "Basic realm=\"\(realm)\", charset=\"UTF-8\""
    }

    /// Compares the two headers without letting the time taken depend on how
    /// many leading bytes agree.
    static func matches(_ offered: String, _ expected: String) -> Bool {
        let offeredBytes = Array(offered.utf8)
        let expectedBytes = Array(expected.utf8)
        var difference = UInt8(offeredBytes.count == expectedBytes.count ? 0 : 1)
        for index in 0..<expectedBytes.count {
            let byte = index < offeredBytes.count ? offeredBytes[index] : 0
            difference |= byte ^ expectedBytes[index]
        }
        return difference == 0
    }

    /// The `Authorization` header value a user name and password produce, or
    /// `nil` when either cannot be carried in one.
    @objc(basicHeaderForUsername:password:)
    public static func basicHeader(username: String, password: String) -> String? {
        guard !username.isEmpty, !password.isEmpty, !username.contains(":") else { return nil }
        let joined = username + ":" + password
        guard !joined.contains("\r"), !joined.contains("\n") else { return nil }
        return "Basic " + Data(joined.utf8).base64EncodedString()
    }

    /// What the interface exposes once it leaves loopback, in the words used by
    /// the preference pane and by the documentation.
    @objc public static var exposureWarning: String {
        return NSLocalizedString(
            "While the XML-RPC interface answers other interfaces, any host that can reach this "
                + "machine and knows the password can list the database, including patient names and "
                + "identifiers, retrieve studies, open URLs and quit Horos.",
            comment: "XML-RPC remote access warning")
    }
}

/// The credential the XML-RPC interface checks against, kept in the keychain
/// rather than in the preferences file.
///
/// Only the expected `Authorization` header is stored, so the password never
/// exists in the defaults and the comparison is one string against another.
@objc(HorosXMLRPCServerCredential)
public final class XMLRPCServerCredential: NSObject {
    private static let readLock = NSLock()
    private static let service = "org.horosproject.horos.xmlrpc"
    private static let account = "server"

    private static var query: [String: Any] {
        return [kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: account]
    }

    private static func failure(_ status: OSStatus) -> NSError {
        return NSError(domain: "HorosXMLRPCServerCredential", code: Int(status), userInfo: [
            NSLocalizedDescriptionKey: NSLocalizedString(
                "The XML-RPC password could not be read from the keychain. Set it again in the "
                    + "Listener preferences or unlock the keychain.",
                comment: "XML-RPC keychain failure")])
    }

    /// Stores the credential for `username` and `password`.
    @objc(saveUsername:password:error:)
    public static func save(username: String, password: String) throws {
        guard let header = XMLRPCServerAccess.basicHeader(username: username, password: password) else {
            throw failure(errSecParam)
        }
        var item = query
        let value = [kSecValueData as String: Data(header.utf8)]
        let status = SecItemUpdate(item as CFDictionary, value as CFDictionary)
        if status == errSecItemNotFound {
            item.merge(value) { _, new in new }
            item[kSecAttrSynchronizable as String] = false
            item[kSecAttrLabel as String] = XMLRPCServerAccess.realm
            let added = SecItemAdd(item as CFDictionary, nil)
            guard added == errSecSuccess else { throw failure(added) }
        } else if status != errSecSuccess {
            throw failure(status)
        }
    }

    /// The expected `Authorization` header, or `nil` when none is stored.
    ///
    /// This is read on the connection thread for every request, so it never
    /// puts up a keychain dialog: a credential that cannot be read without one
    /// counts as absent, which keeps the listener on loopback instead of
    /// blocking a socket thread on a modal panel.
    @objc public static var header: String? {
        var item = query
        item[kSecReturnData as String] = true
        item[kSecMatchLimit as String] = kSecMatchLimitOne
        readLock.lock()
        defer { readLock.unlock() }
        var interactionAllowed: DarwinBoolean = false
        guard SecKeychainGetUserInteractionAllowed(&interactionAllowed) == errSecSuccess,
              SecKeychainSetUserInteractionAllowed(false) == errSecSuccess else { return nil }
        defer { SecKeychainSetUserInteractionAllowed(interactionAllowed.boolValue) }
        var result: CFTypeRef?
        guard SecItemCopyMatching(item as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data,
              let header = String(data: data, encoding: .utf8),
              !header.isEmpty else { return nil }
        return header
    }

    /// Whether a credential exists, without copying it.
    @objc public static var isConfigured: Bool {
        return header != nil
    }

    /// Forgets the credential. The listener returns to loopback on its next
    /// start.
    @objc(removeAndReturnError:)
    public static func remove() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw failure(status) }
    }
}
