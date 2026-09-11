import Foundation
import Darwin

/// Validation at the Locations field editor, before Cocoa bindings persist a value.
@objc(HorosDICOMNodeFormatter)
public final class DICOMNodeFormatter: Formatter {
    private let field: String
    @objc(initWithField:)
    public init(field: String) { self.field = field; super.init() }
    required init?(coder: NSCoder) { field = coder.decodeObject(forKey: "field") as? String ?? "Address"; super.init(coder: coder) }
    public override func encode(with coder: NSCoder) { super.encode(with: coder); coder.encode(field, forKey: "field") }
    public override func string(for obj: Any?) -> String? {
        if let value = obj as? String { return value }
        return (obj as? NSNumber)?.stringValue
    }
    /// Adjacent valid port for the TLS listener; never crosses TCP's upper bound.
    @objc(alternativePortTo:)
    public static func alternativePort(to port: Int) -> Int {
        guard (1...65535).contains(port) else { return 11113 }
        return port == 65535 ? 65534 : port + 1
    }
    @objc public func validationError(_ input: String) -> String? {
        let value = input.trimmingCharacters(in: .whitespacesAndNewlines)
        switch field {
        case "Port":
            guard !value.isEmpty, value.utf8.allSatisfy({ (48...57).contains($0) }),
                  let port = Int(value), (1...65535).contains(port) else {
                return NSLocalizedString("Enter a whole port number from 1 to 65535.", comment: "DICOM node port validation")
            }
        case "AETitle":
            guard !value.isEmpty, value.utf8.count <= 16,
                  value.utf8.allSatisfy({ (32...126).contains($0) && $0 != 92 }) else {
                return NSLocalizedString("Enter an AE Title of 1 to 16 ASCII characters, without a backslash.", comment: "DICOM AE validation")
            }
        default:
            guard Self.isHost(value) else {
                return NSLocalizedString("Enter an IP address or host name without a URL scheme, path or port. Enter the port in the Port column.", comment: "DICOM node address validation")
            }
        }
        return nil
    }
    private static func isHost(_ value: String) -> Bool {
        guard !value.isEmpty, !value.contains(where: { $0.isWhitespace }) else { return false }
        var ipv4 = in_addr(), ipv6 = in6_addr()
        if value.withCString({ inet_pton(AF_INET, $0, &ipv4) }) == 1 { return true }
        // Keep an IPv6 interface scope, e.g. fe80::1%en0, without resolving DNS.
        let scoped = value.split(separator: "%", omittingEmptySubsequences: false)
        if scoped.count <= 2, let address = scoped.first,
           String(address).withCString({ inet_pton(AF_INET6, $0, &ipv6) }) == 1 {
            return scoped.count == 1 || (!scoped[1].isEmpty && scoped[1].allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" || $0 == ".") })
        }
        if value.allSatisfy({ $0.isNumber || $0 == "." }) { return false }
        let host = value.hasSuffix(".") ? String(value.dropLast()) : value
        guard host.utf8.count <= 253 else { return false }
        return host.split(separator: ".", omittingEmptySubsequences: false).allSatisfy { label in
            !label.isEmpty && label.utf8.count <= 63 && label.first != "-" && label.last != "-" &&
            label.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "-") }
        }
    }
    public override func getObjectValue(_ obj: AutoreleasingUnsafeMutablePointer<AnyObject?>?, for string: String,
                                       errorDescription error: AutoreleasingUnsafeMutablePointer<NSString?>?) -> Bool {
        if let message = validationError(string) { error?.pointee = message as NSString; return false }
        let value = string.trimmingCharacters(in: .whitespacesAndNewlines)
        obj?.pointee = field == "Port" ? NSNumber(value: Int(value)!) : value as NSString
        return true
    }
}
