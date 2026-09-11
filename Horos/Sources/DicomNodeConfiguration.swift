import Foundation

/// What a DICOM node is configured as, written so two of them can be compared.
///
/// When one workstation can retrieve and another cannot, the difference is in
/// the configuration — the calling AE title, the called one, the address, the
/// port, the retrieve method, whether TLS is on — and the failure said only the
/// called AE title, the host and the port. Everything else had to be read off
/// two screens side by side.
///
/// This writes the whole of it, always in the same order and always with every
/// field present, so the block from a working machine and the block from a
/// failing one differ only where the configurations do.
@objc(HorosDicomNodeConfiguration)
public final class DicomNodeConfiguration: NSObject {
    @objc(addressForServer:)
    public static func address(forServer server: [String: Any]) -> String {
        guard (server["retrieveMode"] as? NSNumber)?.intValue == 3 else {
            return "\(server["Address"] ?? ""):\(server["Port"] ?? "")"
        }
        guard let raw = server["DICOMwebURL"] as? String,
              var url = URLComponents(string: raw), url.host != nil else { return "DICOMweb" }
        url.user = nil; url.password = nil; url.query = nil; url.fragment = nil
        return url.string ?? "DICOMweb"
    }

    /// The retrieve modes, as `DCMNetServiceDelegate` numbers them.
    static func retrieveMode(_ value: Int) -> String {
        switch value {
        case 0: return "C-MOVE"
        case 1: return "C-GET"
        case 2: return "WADO"
        case 3: return "DICOMweb"
        default: return "unknown (\(value))"
        }
    }

    /// The transfer syntax choices, as the node editor numbers them.
    static func transferSyntax(_ value: Int) -> String {
        switch value {
        case 0: return "explicit little endian"
        case 1: return "JPEG 2000 lossless"
        case 2: return "JPEG 2000 lossy 10:1"
        case 3: return "JPEG 2000 lossy 20:1"
        case 4: return "JPEG 2000 lossy 50:1"
        case 5: return "JPEG lossless"
        case 6: return "JPEG high quality"
        case 7: return "JPEG medium quality"
        case 8: return "JPEG low quality"
        case 9: return "implicit little endian"
        case 10: return "RLE"
        default: return "choice \(value)"
        }
    }

    static func text(_ server: [String: Any], _ key: String) -> String? {
        if let value = server[key] as? String, !value.isEmpty { return value }
        if let value = server[key] as? NSNumber { return value.stringValue }
        return nil
    }

    static func number(_ server: [String: Any], _ key: String) -> Int? {
        if let value = server[key] as? NSNumber { return value.intValue }
        if let value = server[key] as? String, let parsed = Int(value) { return parsed }
        return nil
    }

    /// The settings, in a fixed order, one per line.
    @objc(settingsForServer:callingAETitle:)
    public static func settings(forServer server: [String: Any],
                                callingAETitle: String?) -> [String: String] {
        var settings: [String: String] = [:]
        settings["calling AE title"] = callingAETitle ?? "(none)"
        settings["called AE title"] = text(server, "AETitle") ?? "(none)"
        settings["address"] = text(server, "Address") ?? "(none)"
        settings["port"] = text(server, "Port") ?? "(none)"
        settings["retrieve"] = retrieveMode(number(server, "retrieveMode") ?? 0)
        settings["transfer syntax"] = transferSyntax(number(server, "TransferSyntax") ?? 0)
        settings["TLS"] = (number(server, "TLSEnabled") ?? 0) != 0 ? "on" : "off"
        settings["activated"] = (server["Activated"] == nil
                                 || (number(server, "Activated") ?? 1) != 0) ? "yes" : "no"
        if (number(server, "retrieveMode") ?? 0) == 2 {
            settings["WADO url"] = text(server, "WADOUrl") ?? "(none)"
            settings["WADO port"] = text(server, "WADOPort") ?? "(none)"
            settings["WADO https"] = (number(server, "WADOhttps") ?? 0) != 0 ? "on" : "off"
            settings["WADO transfer syntax"] = transferSyntax(number(server, "WADOTransferSyntax") ?? 0)
        }
        return settings
    }

    static let order = ["calling AE title", "called AE title", "address", "port", "retrieve",
                        "transfer syntax", "TLS", "activated",
                        "WADO url", "WADO port", "WADO https", "WADO transfer syntax"]

    /// The block that goes in a failure report and in the log.
    @objc(descriptionForServer:callingAETitle:)
    public static func description(forServer server: [String: Any],
                                   callingAETitle: String?) -> String {
        let settings = self.settings(forServer: server, callingAETitle: callingAETitle)
        let lines = order.compactMap { key -> String? in
            guard let value = settings[key] else { return nil }
            return "  \(key.padding(toLength: 21, withPad: " ", startingAt: 0))\(value)"
        }
        return (["Node configuration:"] + lines).joined(separator: "\n")
    }

    /// Where two configurations differ, so the block from a machine that works
    /// and the block from one that does not can be compared without reading
    /// them line by line.
    @objc(differencesBetweenServer:andServer:callingAETitle:otherCallingAETitle:)
    public static func differences(betweenServer first: [String: Any],
                                   andServer second: [String: Any],
                                   callingAETitle: String?,
                                   otherCallingAETitle: String?) -> [String] {
        let a = settings(forServer: first, callingAETitle: callingAETitle)
        let b = settings(forServer: second, callingAETitle: otherCallingAETitle)
        var differences: [String] = []
        for key in order {
            let left = a[key]
            let right = b[key]
            if left == nil && right == nil { continue }
            if left != right {
                differences.append("\(key): \(left ?? "(not set)") vs \(right ?? "(not set)")")
            }
        }
        return differences
    }
}
