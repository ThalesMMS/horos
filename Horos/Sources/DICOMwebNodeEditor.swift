import AppKit

/// How a DICOMweb node is edited (#380 A).
///
/// A node in `SERVERS` carries far more than DICOMweb: AE title, address,
/// port, transfer syntax, TLS, WADO. Editing the DICOMweb half must leave all
/// of that alone, so the edit is a *merge* into the node that was there, and a
/// node is recognised by the identity its DIMSE half already has.
@objc(HorosDICOMwebNodeEditor)
public final class DICOMwebNodeEditor: NSObject {
    /// What a DICOMweb edit may write, and nothing else.
    @objc public static let editedKeys = ["DICOMwebURL", "DICOMwebCredentialID", "retrieveMode", "Send"]

    /// The identity of a node among the others: its AE title, address and port.
    /// Two entries with the same three are the same node, whatever else they
    /// carry, so an edit finds its target without matching on description.
    @objc(identityOfNode:)
    public static func identity(of node: NSDictionary) -> String {
        func text(_ key: String) -> String {
            if let value = node[key] as? String { return value.trimmingCharacters(in: .whitespacesAndNewlines) }
            if let value = node[key] as? NSNumber { return value.stringValue }
            return ""
        }
        return [text("AETitle"), text("Address"), text("Port")].joined(separator: "|").uppercased()
    }

    /// The node as it must be saved after an edit: everything the node already
    /// had, with only the DICOMweb keys replaced. `credentialIdentifier` nil
    /// removes the stored credential reference.
    @objc(nodeMergingInto:url:credentialIdentifier:)
    public static func merging(into original: NSDictionary, url: String, credentialIdentifier: String?) -> NSDictionary {
        let node = (original.mutableCopy() as? NSMutableDictionary) ?? NSMutableDictionary()
        node["DICOMwebURL"] = url
        node["retrieveMode"] = 3
        node["Send"] = false // The pilot has no STOW operation.
        if let identifier = credentialIdentifier, !identifier.isEmpty {
            node["DICOMwebCredentialID"] = identifier
        } else {
            node.removeObject(forKey: "DICOMwebCredentialID")
        }
        return node
    }
    @objc(editNode:)
    public static func edit(_ original: NSDictionary) -> NSDictionary? {
        precondition(Thread.isMainThread)
        let alert = NSAlert()
        alert.messageText = NSLocalizedString("DICOMweb Node", comment: "")
        alert.informativeText = NSLocalizedString("Configure QIDO queries and WADO-RS retrieval. Credentials are stored in Keychain. DIMSE settings are retained separately.", comment: "")
        alert.addButton(withTitle: NSLocalizedString("Save", comment: ""))
        alert.addButton(withTitle: NSLocalizedString("Cancel", comment: ""))
        let endpoint = NSTextField(string: original["DICOMwebURL"] as? String ?? "https://")
        endpoint.setAccessibilityLabel("DICOMweb URL")
        endpoint.widthAnchor.constraint(equalToConstant: 400).isActive = true
        let authentication = NSPopUpButton()
        authentication.addItems(withTitles: ["Keep stored credentials", "No authentication", "Username and password", "Bearer token"])
        let existing = original["DICOMwebCredentialID"] as? String ?? ""
        authentication.selectItem(at: existing.isEmpty ? 1 : 0)
        authentication.setAccessibilityLabel("DICOMweb authentication")
        let username = NSTextField(string: "")
        username.setAccessibilityLabel("DICOMweb username")
        let password = NSSecureTextField(string: "")
        password.setAccessibilityLabel("DICOMweb password")
        let token = NSSecureTextField(string: "")
        token.setAccessibilityLabel("DICOMweb bearer token")
        let grid = NSGridView(views: [
            [NSTextField(labelWithString: "URL:"), endpoint],
            [NSTextField(labelWithString: "Authentication:"), authentication],
            [NSTextField(labelWithString: "Username:"), username],
            [NSTextField(labelWithString: "Password:"), password],
            [NSTextField(labelWithString: "Bearer token:"), token]
        ])
        grid.rowSpacing = 10
        grid.column(at: 0).xPlacement = .trailing
        grid.setFrameSize(grid.fittingSize)
        alert.accessoryView = grid
        while alert.runModal() == .alertFirstButtonReturn {
            do {
                let url = endpoint.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
                _ = try DICOMwebClient(endpoint: url, credentialIdentifier: "", timeout: 60)
                let identifier = existing.isEmpty ? UUID().uuidString : existing
                var credential: String? = existing.isEmpty ? nil : existing
                switch authentication.indexOfSelectedItem {
                case 0:
                    guard !existing.isEmpty else { throw DICOMwebClient.failure(1, "Choose an authentication method.") }
                case 1:
                    if !existing.isEmpty { try DICOMwebCredentials.remove(identifier: existing) }
                    credential = nil
                case 2:
                    guard !username.stringValue.isEmpty, !username.stringValue.contains(":"), !password.stringValue.isEmpty else { throw DICOMwebClient.failure(1, "Enter a username and password. The username cannot contain a colon.") }
                    try DICOMwebCredentials.save(identifier: identifier, username: username.stringValue, password: password.stringValue, bearerToken: "")
                    credential = identifier
                case 3:
                    guard !token.stringValue.isEmpty else { throw DICOMwebClient.failure(1, "Enter a bearer token.") }
                    try DICOMwebCredentials.save(identifier: identifier, username: "", password: "", bearerToken: token.stringValue)
                    credential = identifier
                default: throw DICOMwebClient.failure(1, "Choose an authentication method.")
                }
                password.stringValue = ""; token.stringValue = ""
                return merging(into: original, url: url, credentialIdentifier: credential)
            } catch {
                alert.informativeText = (error as NSError).localizedDescription
            }
        }
        password.stringValue = ""; token.stringValue = ""
        return nil
    }
}
