import AppKit
import Darwin
import Foundation

/// Presence and coordinated I/O for on-demand cloud files (OneDrive and others).
///
/// Import and export used to treat every path as a local file. A File Provider
/// placeholder can exist, have a size, and still have no bytes. Copying it
/// produced an incomplete destination that was then indexed or exported.
///
/// This helper classifies local / hydrated / placeholder / offline, coordinates
/// the read or write with `NSFileCoordinator`, and refuses to start a copy when
/// the source still needs hydration. It does not claim that an active database
/// is safe inside a cloud folder.
@objc(HorosCloudFileAccess)
public final class CloudFileAccess: NSObject {
    @objc public static let presenceLocal = "local"
    @objc public static let presenceHydrated = "hydrated"
    @objc public static let presencePlaceholder = "placeholder"
    @objc public static let presenceOffline = "offline"

    @objc public static let errorDomain = "HorosCloudFileAccess"
    @objc public static let hydrationErrorCode = 1651
    @objc public static let offlineErrorCode = 1652
    @objc public static let coordinationErrorCode = 1653

    /// Synthetic-fixture xattr used by focused tests. Production also honours
    /// File Provider / ubiquitous status and allocated-size placeholders.
    @objc public static let fixturePresenceAttribute = "horos.cloud.presence"

    @objc public static let ignoredWarningDefaultsKey = "CLOUD_ACTIVE_DATABASE_WARNING_IGNORED"

    /// Provider label for a path, or nil when it is ordinary local storage.
    @objc(providerNameForPath:)
    public static func providerName(forPath path: String?) -> String? {
        guard let path, !path.isEmpty else { return nil }
        let components = (path as NSString).standardizingPath.split(separator: "/").map(String.init)
        if let index = components.firstIndex(of: "CloudStorage"), index + 1 < components.count {
            return providerLabel(forContainer: components[index + 1])
        }
        if components.contains("Mobile Documents") {
            return "iCloud"
        }
        if components.contains(where: { $0.compare("OneDrive", options: .caseInsensitive) == .orderedSame })
            || components.contains(where: { $0.lowercased().hasPrefix("onedrive -") }) {
            return "OneDrive"
        }
        return nil
    }

    /// One of local, hydrated, placeholder, offline.
    @objc(presenceOfPath:)
    public static func presence(ofPath path: String?) -> String {
        guard let path, !path.isEmpty else { return presenceLocal }
        if let fixture = fixturePresence(at: path) {
            return fixture
        }

        let provider = providerName(forPath: path)
        var isDirectory: ObjCBool = false
        let exists = FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
        if provider == nil {
            return presenceLocal
        }
        if !exists {
            return presenceOffline
        }
        if isDirectory.boolValue {
            return presenceHydrated
        }

        let url = URL(fileURLWithPath: path)
        if let values = try? url.resourceValues(forKeys: [
            .ubiquitousItemDownloadingStatusKey,
            .ubiquitousItemIsDownloadingKey,
            .fileSizeKey,
            .fileAllocatedSizeKey,
            .isReadableKey
        ]) {
            if values.ubiquitousItemDownloadingStatus == .notDownloaded
                || values.ubiquitousItemIsDownloading == true {
                return presencePlaceholder
            }
            if let size = values.fileSize, let allocated = values.fileAllocatedSize,
               size > 0, allocated == 0 {
                return presencePlaceholder
            }
            if values.isReadable == false {
                return presenceOffline
            }
        }

        if hasFileProviderPlaceholderAttribute(at: path) {
            return presencePlaceholder
        }
        if FileManager.default.isReadableFile(atPath: path) {
            return presenceHydrated
        }
        return presenceOffline
    }

    /// Refuse a copy that would publish an unhydrated source. Coordinates
    /// provider I/O when the path is in a known cloud container.
    @objc(prepareCopyFromPath:toPath:error:)
    public static func prepareCopy(fromPath source: String, toPath destination: String, error: NSErrorPointer) -> Bool {
        let sourcePresence = presence(ofPath: source)
        if sourcePresence == presencePlaceholder || sourcePresence == presenceOffline {
            if let error {
                error.pointee = hydrationError(presence: sourcePresence, path: source)
            }
            return false
        }

        if providerName(forPath: source) != nil {
            if !coordinateReading(path: source, error: error) {
                return false
            }
            let after = presence(ofPath: source)
            if after == presencePlaceholder || after == presenceOffline {
                if let error {
                    error.pointee = hydrationError(presence: after, path: source)
                }
                return false
            }
        }

        if providerName(forPath: destination) != nil {
            let directory = (destination as NSString).deletingLastPathComponent
            if !coordinateWriting(path: directory, error: error) {
                return false
            }
        }
        return true
    }

    @objc(shouldWarnAboutActiveDatabaseAtPath:)
    public static func shouldWarnAboutActiveDatabase(atPath path: String?) -> Bool {
        guard let path, providerName(forPath: path) != nil else { return false }
        if path.contains(".nosync") { return false }
        if UserDefaults.standard.bool(forKey: ignoredWarningDefaultsKey) { return false }
        return true
    }

    /// Names the risk. Does not recommend keeping an active database on cloud storage.
    @objc(activeDatabaseWarningForPath:)
    public static func activeDatabaseWarning(forPath path: String?) -> String {
        let provider = providerName(forPath: path) ?? "a cloud provider"
        return String(format: NSLocalizedString(
            "This Horos database is inside a %@ folder. An active database has not been validated on cloud storage. Do not keep the live database on OneDrive or another cloud provider. Import and export of on-demand files also require the files to be available offline; incomplete copies are not published.",
            comment: "active database in cloud folder"), provider)
    }

    @objc(presentActiveDatabaseWarningForPath:)
    public static func presentActiveDatabaseWarning(forPath path: String) {
        let message = activeDatabaseWarning(forPath: path)
        NSLog("HorosCloudFileAccess: %@", message)
        DispatchQueue.main.async {
            presentWarningOnMain(message, attemptsLeft: 8)
        }
    }

    @objc public static func resetIgnoredWarningForTests() {
        UserDefaults.standard.removeObject(forKey: ignoredWarningDefaultsKey)
    }

    @objc(setFixturePresence:atPath:error:)
    public static func setFixturePresence(_ value: String, atPath path: String) throws {
        try setExtendedAttribute(fixturePresenceAttribute, value: value, at: path)
    }

    private static func providerLabel(forContainer folder: String) -> String {
        let lower = folder.lowercased()
        if lower.contains("onedrive") { return "OneDrive" }
        if lower.contains("dropbox") { return "Dropbox" }
        if lower.contains("google") { return "Google Drive" }
        if lower.contains("box") { return "Box" }
        if lower.contains("icloud") { return "iCloud" }
        return folder
    }

    private static func fixturePresence(at path: String) -> String? {
        guard let value = extendedAttribute(fixturePresenceAttribute, at: path) else { return nil }
        switch value {
        case presenceHydrated, presencePlaceholder, presenceOffline, presenceLocal:
            return value
        default:
            return nil
        }
    }

    private static func hasFileProviderPlaceholderAttribute(at path: String) -> Bool {
        for name in extendedAttributeNames(at: path) {
            let lower = name.lowercased()
            if lower.contains("fileprovider.fpfs#p")
                || lower.contains("fileprovider.placeholder")
                || lower.hasPrefix("com.microsoft.onedrive") && lower.contains("offline") {
                return true
            }
        }
        return false
    }

    private static func hydrationError(presence: String, path: String) -> NSError {
        let provider = providerName(forPath: path) ?? "cloud provider"
        let reason: String
        let code: Int
        if presence == presenceOffline {
            code = offlineErrorCode
            reason = String(format: NSLocalizedString(
                "The file is offline or not available from %@. Make it available offline and retry. The original file was left unchanged.",
                comment: "offline cloud file"), provider)
        } else {
            code = hydrationErrorCode
            reason = String(format: NSLocalizedString(
                "The file is a %@ placeholder and has not been hydrated. Make it available offline and retry. The original file was left unchanged.",
                comment: "placeholder cloud file"), provider)
        }
        return NSError(domain: errorDomain, code: code, userInfo: [
            NSLocalizedDescriptionKey: reason,
            NSLocalizedFailureReasonErrorKey: reason
        ])
    }

    private static func wrapCoordination(_ underlying: NSError, path: String) -> NSError {
        let provider = providerName(forPath: path) ?? "cloud provider"
        let reason = String(format: NSLocalizedString(
            "The %@ file could not be coordinated for reading or writing. Make the files available offline and retry. Existing files were left unchanged.",
            comment: "cloud coordination"), provider)
        return NSError(domain: errorDomain, code: coordinationErrorCode, userInfo: [
            NSLocalizedDescriptionKey: reason,
            NSLocalizedFailureReasonErrorKey: reason,
            NSUnderlyingErrorKey: underlying
        ])
    }

    private static func coordinateReading(path: String, error: NSErrorPointer) -> Bool {
        let url = URL(fileURLWithPath: path)
        let coordinator = NSFileCoordinator(filePresenter: nil)
        var coordinatorError: NSError?
        var ok = false
        coordinator.coordinate(readingItemAt: url, options: [], error: &coordinatorError) { _ in
            ok = true
        }
        if let coordinatorError {
            if let error { error.pointee = wrapCoordination(coordinatorError, path: path) }
            return false
        }
        return ok
    }

    private static func coordinateWriting(path: String, error: NSErrorPointer) -> Bool {
        let url = URL(fileURLWithPath: path)
        let coordinator = NSFileCoordinator(filePresenter: nil)
        var coordinatorError: NSError?
        var ok = false
        coordinator.coordinate(writingItemAt: url, options: [.forMerging], error: &coordinatorError) { _ in
            ok = true
        }
        if let coordinatorError {
            if let error { error.pointee = wrapCoordination(coordinatorError, path: path) }
            return false
        }
        return ok
    }

    private static func presentWarningOnMain(_ message: String, attemptsLeft: Int) {
        let alert = NSAlert()
        alert.messageText = NSLocalizedString(
            "Cloud storage is not validated for an active database",
            comment: "cloud database warning title")
        alert.informativeText = message
        alert.addButton(withTitle: NSLocalizedString("OK", comment: ""))
        alert.addButton(withTitle: NSLocalizedString("Don’t warn again", comment: ""))
        if let window = NSApp.mainWindow ?? NSApp.windows.first(where: { $0.isVisible }) {
            alert.beginSheetModal(for: window) { response in
                if response == .alertSecondButtonReturn {
                    UserDefaults.standard.set(true, forKey: ignoredWarningDefaultsKey)
                }
            }
            return
        }
        guard attemptsLeft > 0 else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
            presentWarningOnMain(message, attemptsLeft: attemptsLeft - 1)
        }
    }

    private static func setExtendedAttribute(_ name: String, value: String, at path: String) throws {
        let result = path.withCString { pathPointer in
            name.withCString { namePointer in
                value.withCString { valuePointer in
                    setxattr(pathPointer, namePointer, valuePointer, strlen(valuePointer), 0, 0)
                }
            }
        }
        if result != 0 {
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno), userInfo: [
                NSLocalizedDescriptionKey: "Could not set \(name) on \(path)"
            ])
        }
    }

    private static func extendedAttribute(_ name: String, at path: String) -> String? {
        let length = path.withCString { pathPointer in
            name.withCString { namePointer in
                getxattr(pathPointer, namePointer, nil, 0, 0, 0)
            }
        }
        guard length > 0 else { return nil }
        var buffer = [Int8](repeating: 0, count: Int(length) + 1)
        let read = path.withCString { pathPointer in
            name.withCString { namePointer in
                getxattr(pathPointer, namePointer, &buffer, Int(length), 0, 0)
            }
        }
        guard read > 0 else { return nil }
        return String(cString: buffer)
    }

    private static func extendedAttributeNames(at path: String) -> [String] {
        let length = path.withCString { getxattrNamesSize($0) }
        guard length > 0 else { return [] }
        var buffer = [Int8](repeating: 0, count: Int(length))
        let read = path.withCString { listxattr($0, &buffer, Int(length), 0) }
        guard read > 0 else { return [] }
        return buffer.split(separator: 0).compactMap { chunk in
            String(decoding: chunk.map { UInt8(bitPattern: $0) }, as: UTF8.self)
        }.filter { !$0.isEmpty }
    }

    private static func getxattrNamesSize(_ path: UnsafePointer<CChar>) -> ssize_t {
        listxattr(path, nil, 0, 0)
    }
}
