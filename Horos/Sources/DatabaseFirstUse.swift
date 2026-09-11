import AppKit

/// Chooses a storage location before the first database is opened. Existing
/// installations and explicit launch locations keep their configured behavior.
@objc(HorosDatabaseFirstUse)
public final class DatabaseFirstUse: NSObject {
    static let completedKey = "DatabaseLocationChoiceCompleted"
    static let pendingKey = "DatabaseLocationChoicePending"

    static func needsChoice(defaults: UserDefaults, documents: URL) -> Bool {
        let arguments = defaults.volatileDomain(forName: UserDefaults.argumentDomain)
        if arguments["DATABASELOCATION"] != nil || arguments["DEFAULT_DATABASELOCATION"] != nil ||
            arguments["DATABASELOCATIONURL"] != nil || arguments["DEFAULT_DATABASELOCATIONURL"] != nil {
            return false
        }
        if defaults.bool(forKey: completedKey) || defaults.integer(forKey: "DEFAULT_DATABASELOCATION") != 0 {
            return false
        }
        if defaults.bool(forKey: pendingKey) { return true }
        // Even a damaged or partially created database belongs to an existing
        // installation. Location setup must not redirect it to a new empty one.
        return !FileManager.default.fileExists(atPath: documents.appendingPathComponent("Horos Data").path)
    }

    private static var pendingDocuments: URL?

    @objc(prepareWithAlternateDefault:)
    public static func prepare(alternateDefault: String?) {
        guard alternateDefault.map({ !FileManager.default.fileExists(atPath: $0) }) ?? true,
              let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first,
              needsChoice(defaults: .standard, documents: documents) else { return }
        UserDefaults.standard.set(true, forKey: pendingKey)
        pendingDocuments = documents
    }

    @objc public static var hasPendingChoice: Bool { pendingDocuments != nil }

    // Present after class initialization, when AppKit can service accessibility
    // and window events, but before the browser opens its database.
    @objc(choosePreparedLocation)
    public static func choosePreparedLocation() -> Bool {
        guard let documents = pendingDocuments else { return true }
        let chosen = chooseLocation(defaults: .standard, documents: documents)
        pendingDocuments = nil
        return chosen
    }

    static func chooseLocation(defaults: UserDefaults, documents: URL) -> Bool {
        while true {
            let alert = NSAlert()
            alert.messageText = NSLocalizedString("Choose where to store your database", comment: "First use")
            alert.informativeText = String(format: NSLocalizedString("Horos stores its index and imported images in a Horos Data folder. This folder grows as you import studies.\n\nDocuments: %@\n\nYou can choose another folder or drive. Choosing a location does not move or duplicate existing data. Change it later in Settings > Database.", comment: "First use storage explanation"), documents.path)
            alert.addButton(withTitle: NSLocalizedString("Use Documents", comment: "First use"))
            alert.addButton(withTitle: NSLocalizedString("Choose Folder…", comment: "First use"))
            alert.addButton(withTitle: NSLocalizedString("Quit", comment: "First use"))
            let response = alert.runModal()
            if response == .alertThirdButtonReturn {
                defaults.synchronize()
                return false
            }
            var location = documents
            if response == .alertSecondButtonReturn {
                let panel = NSOpenPanel()
                panel.title = NSLocalizedString("Choose database folder", comment: "First use")
                panel.message = NSLocalizedString("Select a folder for Horos Data, or select an existing database to reopen it. No data will be moved or copied.", comment: "First use")
                panel.canChooseFiles = false
                panel.canChooseDirectories = true
                panel.canCreateDirectories = true
                panel.allowsMultipleSelection = false
                panel.directoryURL = documents
                guard panel.runModal() == .OK, let selected = panel.url else { continue }
                location = selected
            }
            if CloudFileAccess.providerName(forPath: location.path) != nil {
                let warn = NSAlert()
                warn.messageText = NSLocalizedString(
                    "Cloud storage is not validated for an active database",
                    comment: "First use cloud warning")
                warn.informativeText = CloudFileAccess.activeDatabaseWarning(forPath: location.path)
                warn.addButton(withTitle: NSLocalizedString("Choose a different folder", comment: "First use"))
                warn.addButton(withTitle: NSLocalizedString("Continue anyway", comment: "First use"))
                if warn.runModal() == .alertFirstButtonReturn {
                    continue
                }
            }
            // Store Documents explicitly too: subsequent launches reopen the
            // same selected folder through the existing location contract.
            defaults.set(location.path, forKey: "DEFAULT_DATABASELOCATIONURL")
            defaults.set(1, forKey: "DEFAULT_DATABASELOCATION")
            defaults.set(true, forKey: completedKey)
            defaults.removeObject(forKey: pendingKey)
            defaults.synchronize()
            return true
        }
    }
}
