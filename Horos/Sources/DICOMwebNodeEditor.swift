import AppKit

@objc(HorosDICOMwebNodeEditor)
public final class DICOMwebNodeEditor: NSObject {
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
                let node = original.mutableCopy() as! NSMutableDictionary
                let identifier = existing.isEmpty ? UUID().uuidString : existing
                switch authentication.indexOfSelectedItem {
                case 0:
                    guard !existing.isEmpty else { throw DICOMwebClient.failure(1, "Choose an authentication method.") }
                case 1:
                    if !existing.isEmpty { try DICOMwebCredentials.remove(identifier: existing) }
                    node.removeObject(forKey: "DICOMwebCredentialID")
                case 2:
                    guard !username.stringValue.isEmpty, !username.stringValue.contains(":"), !password.stringValue.isEmpty else { throw DICOMwebClient.failure(1, "Enter a username and password. The username cannot contain a colon.") }
                    try DICOMwebCredentials.save(identifier: identifier, username: username.stringValue, password: password.stringValue, bearerToken: "")
                    node["DICOMwebCredentialID"] = identifier
                case 3:
                    guard !token.stringValue.isEmpty else { throw DICOMwebClient.failure(1, "Enter a bearer token.") }
                    try DICOMwebCredentials.save(identifier: identifier, username: "", password: "", bearerToken: token.stringValue)
                    node["DICOMwebCredentialID"] = identifier
                default: throw DICOMwebClient.failure(1, "Choose an authentication method.")
                }
                node["DICOMwebURL"] = url
                node["retrieveMode"] = 3
                node["Send"] = false // The pilot has no STOW operation.
                password.stringValue = ""; token.stringValue = ""
                return node
            } catch {
                alert.informativeText = (error as NSError).localizedDescription
            }
        }
        password.stringValue = ""; token.stringValue = ""
        return nil
    }
}
