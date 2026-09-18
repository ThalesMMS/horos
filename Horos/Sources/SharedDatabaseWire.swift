import Foundation

/// What the shared-database server accepts from the wire before it consumes,
/// allocates or converts anything (#614).
///
/// Every length and count of this protocol is a 32-bit big-endian integer that
/// the server used as a signed `int`: a negative value asked
/// `_requireDataSize:` for `length + 4`, which overflows, and a string was read
/// with `stringWithUTF8String:` from bytes that need not contain a terminator.
/// The rules live here, stated once, and `O2DatabaseConnection` asks them.
///
/// The limits are sized from the commands the client really sends
/// (`RemoteDicomDatabase.mm`): an upload carries whole files - one may reach the
/// protocol's own 2 GiB bound - in requests the client splits near 32 MiB; every
/// other request is a few strings, or one path per image of a selection.
@objc(HorosSharedDatabaseWire)
public final class SharedDatabaseWire: NSObject {

    /// One string: an object URI, a key, a value, a path, an album description.
    @objc public static let maximumStringLength = 64 << 20

    /// Files in one upload, paths in one fetch or send.
    @objc public static let maximumCount = 1 << 20

    /// One uploaded file: the protocol's length field is a signed 32-bit int.
    @objc public static let maximumFileLength = Int(Int32.max)

    /// What may sit unconsumed in the receive buffer while a request is parsed.
    /// Receiving in blocks bounds each read, not the request: this bounds the
    /// request.
    @objc public static let maximumBufferedBytesAwaitingCommand = 64 << 10
    @objc public static let maximumBufferedBytesForUpload = Int(Int32.max) + (64 << 20)
    @objc public static let maximumBufferedBytesForOtherRequests = 256 << 20

    /// A 32-bit big-endian length or count read as the server always has, as a
    /// signed value; -1 when it is negative or above `maximum`.
    @objc(validatedValue:maximum:)
    public class func validated(_ bigEndian: UInt32, maximum: Int) -> Int {
        let value = Int(Int32(bitPattern: UInt32(bigEndian: bigEndian)))
        return value >= 0 && value <= maximum ? value : -1
    }

    /// Outcome of decoding one string payload (the bytes after its length).
    @objc(HorosSharedDatabaseStringStatus)
    public enum StringStatus: Int {
        case value = 0
        /// Length zero: the client's encoding of nil, distinct from "".
        case null = 1
        case unterminated = 2
        case embeddedNull = 3
        case invalidUTF8 = 4
    }

    /// Decodes a string exactly within `length` bytes at `bytes`: the last byte
    /// must be the terminator, no earlier byte may be one, and the rest must be
    /// UTF-8. Nothing beyond `length` is read.
    @objc(decodeBytes:length:status:)
    public class func decode(_ bytes: UnsafePointer<UInt8>?, length: Int,
                             status: UnsafeMutablePointer<StringStatus>) -> NSString? {
        guard length > 0, let bytes else {
            status.pointee = .null
            return nil
        }
        guard bytes[length - 1] == 0 else {
            status.pointee = .unterminated
            return nil
        }
        if length > 1, memchr(bytes, 0, length - 1) != nil {
            status.pointee = .embeddedNull
            return nil
        }
        guard let string = NSString(bytes: bytes, length: length - 1, encoding: String.Encoding.utf8.rawValue) else {
            status.pointee = .invalidUTF8
            return nil
        }
        status.pointee = .value
        return string
    }
}
