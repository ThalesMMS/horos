import Foundation

/// Reject malformed association fields before authorizing DIMSE service work.
/// The bytes come from DCMTK's public raw A-ASSOCIATE PDU capture API.
enum DIMSEAssociationPolicy {
    static func isValid(_ bytes: [UInt8]) -> Bool {
        guard bytes.count >= 74, bytes[0] == 1 || bytes[0] == 2,
              bytes[2...5].reduce(UInt64(0), { ($0 << 8) | UInt64($1) }) == UInt64(bytes.count - 6)
        else { return false }
        func word(_ offset: Int) -> Int { Int(bytes[offset]) << 8 | Int(bytes[offset + 1]) }
        func uid(_ begin: Int, _ end: Int) -> Bool {
            guard (1...64).contains(end - begin), bytes[begin] != 46, bytes[end - 1] != 46 else { return false }
            var dot = false
            for value in bytes[begin..<end] {
                guard value == 46 || (48...57).contains(value), !(dot && value == 46) else { return false }
                dot = value == 46
            }
            return true
        }
        enum Scope { case association, presentation, user }
        func items(_ begin: Int, _ end: Int, scope: Scope) -> Bool {
            var cursor = begin
            while cursor < end {
                guard end - cursor >= 4 else { return false }
                let kind = bytes[cursor], size = word(cursor + 2)
                let value = cursor + 4
                guard size <= end - value else { return false }
                let next = value + size
                switch (scope, kind) {
                case (.association, 0x10), (.presentation, 0x30), (.presentation, 0x40), (.user, 0x52):
                    guard uid(value, next) else { return false }
                case (.association, 0x20), (.association, 0x21):
                    guard size >= 4, items(value + 4, next, scope: .presentation) else { return false }
                case (.association, 0x50):
                    guard items(value, next, scope: .user) else { return false }
                case (.user, 0x51):
                    guard size == 4 else { return false }
                case (.user, 0x54):
                    guard size >= 4 else { return false }
                    let uidLength = word(value)
                    guard uidLength == size - 4, uid(value + 2, next - 2),
                          bytes[next - 2] <= 1, bytes[next - 1] <= 1 else { return false }
                default:
                    break // Unrecognized extension items remain forward compatible.
                }
                cursor = next
            }
            return cursor == end
        }
        return items(74, bytes.count, scope: .association)
    }
}

@_cdecl("HorosDIMSEAssociationPDUIsValid")
public func validateDIMSEAssociationPDU(_ bytes: UnsafePointer<UInt8>?, _ count: Int) -> Bool {
    guard let bytes, count >= 74, count <= 1024 * 1024 else { return false }
    return DIMSEAssociationPolicy.isValid(Array(UnsafeBufferPointer(start: bytes, count: count)))
}
