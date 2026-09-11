import Foundation
import Security

/// The unguessable half of a web portal credential.
///
/// Three identifiers in the portal used to be built the same way: take a reading
/// of the clock, hash it with MD5, print the digest as hexadecimal. The result is
/// 32 characters long, which suggests 128 bits, and is worth however many bits
/// the *input* had - the set of plausible moments, which is small and which
/// anyone watching the portal can narrow further. The session id was worse still:
/// it hashed `random()`, whose generator is seeded once from `time(NULL)`.
///
/// The hexadecimal shape is kept exactly - upper case, one byte per two
/// characters - because it is carried in a cookie, in URLs and in stored models,
/// and none of those should notice this change. What changes is where the bytes
/// come from.
@objc(HorosWebPortalIdentifier)
public final class WebPortalIdentifier: NSObject {
    /// 128 bits: the entropy the old identifiers' length always implied.
    private static let byteCount = 16
    private static let digits = Array("0123456789ABCDEF".utf8)

    /// A fresh identifier, in the same 32 upper-case hexadecimal characters as before.
    @objc public static func unguessable() -> String {
        return unguessable(byteCount: byteCount)
    }

    @objc(unguessableWithByteCount:)
    public static func unguessable(byteCount: Int) -> String {
        var bytes = [UInt8](repeating: 0, count: max(byteCount, 1))
        if SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) != errSecSuccess {
            // arc4random_buf draws on the same kernel generator and has no failure
            // to report, so this is not a weaker second choice: it is the same
            // source without the error path.
            arc4random_buf(&bytes, bytes.count)
        }
        // One page of the portal renders a token for every study in the list, so
        // this runs a hundred times a request: a table costs 0.12 us where
        // String(format:) per byte costs 11.5 us, measured on this machine.
        var characters = [UInt8]()
        characters.reserveCapacity(bytes.count * 2)
        for byte in bytes {
            characters.append(digits[Int(byte >> 4)])
            characters.append(digits[Int(byte & 0xF)])
        }
        return String(decoding: characters, as: UTF8.self)
    }
}
