import Foundation

/// Versioned per-connection authorization for the legacy shared-database protocol.
/// This envelope authenticates a request; the existing transport is not encrypted.
@objc(HorosSharedDatabaseAuthorization)
public final class SharedDatabaseAuthorization: NSObject {
    private static let header = Data([65, 85, 84, 72, 82, 0]) // AUTHR\0
    private static let publicCommands: Set<String> = ["DBVER", "ISPWD", "PASWD", "AUTHV", "GETDI"]

    @objc public static func isPublicCommand(_ command: String) -> Bool {
        publicCommands.contains(command)
    }

    @objc public static func authenticatedRequest(_ request: Data, password: String) -> Data? {
        let secret = Data(password.utf8)
        guard !secret.isEmpty, secret.count <= 4096, request.count >= 6,
              request.dropFirst(5).first == 0, request.prefix(6) != header else { return nil }
        var result = header
        let count = UInt32(secret.count)
        result.append(contentsOf: [UInt8(count >> 24), UInt8((count >> 16) & 255),
                                  UInt8((count >> 8) & 255), UInt8(count & 255)])
        result.append(secret)
        result.append(request)
        return result
    }

    /// The request an authorization envelope carries, or the request itself when it has
    /// none or the envelope is incomplete. What a request does is decided by this inner
    /// command, not by the `AUTHR` in front of it (#644).
    @objc public static func requestInsideEnvelope(_ request: Data) -> Data {
        guard request.count >= 10, request.prefix(6) == header else { return request }
        let start = request.startIndex
        let count = request[(start + 6)..<(start + 10)].reduce(0) { ($0 << 8) | Int($1) }
        guard count > 0, count <= 4096, request.count >= 10 + count + 6 else { return request }
        return request.subdata(in: (start + 10 + count)..<request.endIndex)
    }

    /// Zero means more data is needed; -1 rejects; positive consumes the envelope.
    /// The six-byte operation header must also be present before authorization.
    @objc public static func authorizedPrefixLength(_ data: Data, password: String?, required: Bool) -> Int {
        guard data.count >= 10 else { return 0 }
        guard data.prefix(6) == header else { return -1 }
        let bytes = Array(data.prefix(4112))
        let count = bytes[6..<10].reduce(0) { ($0 << 8) | Int($1) }
        guard count > 0, count <= 4096 else { return -1 }
        guard data.count >= 10 + count + 6 else { return 0 }
        guard bytes[10 + count + 5] == 0 else { return -1 }
        if !required { return 10 + count }
        guard let password, !password.isEmpty else { return -1 }
        let expected = Array(password.utf8)
        let provided = Array(bytes[10..<10 + count])
        guard expected.count == provided.count else { return -1 }
        var difference: UInt8 = 0
        for index in expected.indices { difference |= expected[index] ^ provided[index] }
        return difference == 0 ? 10 + count : -1
    }
}
