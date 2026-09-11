import ApplicationServices
import AppKit
import Foundation
import Synchronization

/// Creates a recipient-free Mail draft and asks for Automation consent first.
/// The draft is never sent from this path.
@objc(HorosMailDraftComposer)
public final class MailDraftComposer: NSObject {
    public static let mailBundleIdentifier = "com.apple.mail"
    public static let handlerName = "mail_images"
    @MainActor private static var requestPending = false

    private static let subroutineEventClass: AEEventClass = 0x61736372 // 'ascr'
    private static let subroutineEventID: AEEventID = 0x70736272 // 'psbr'
    private static let subroutineNameKeyword: AEKeyword = 0x736E616D // 'snam'

    @objc(messageForErrorInfo:result:)
    public static func message(errorInfo: [AnyHashable: Any]?, result: NSAppleEventDescriptor?) -> String? {
        if errorInfo == nil && result == nil {
            return NSLocalizedString("Horos could not prepare the Mail draft. Check that Mail is available and retry the export. If the problem persists, reinstall Horos to restore its Mail export script.", comment: "")
        }
        let code: Int
        if let errorInfo {
            code = (errorInfo[NSAppleScript.errorNumber] as? NSNumber)?.intValue ?? 0
        } else {
            code = Int(result?.int32Value ?? 0)
        }
        if errorInfo == nil, let result, result.int32Value == 0 { return nil }
        if code == -1743 || code == -1744 {
            return NSLocalizedString("Mail access was denied. Allow Horos to control Mail in System Settings > Privacy & Security > Automation, then retry the export.", comment: "")
        }
        if code == -1712 {
            return NSLocalizedString("Horos did not receive a reply from Mail in time (error -1712). If macOS asked for Automation permission, allow Horos to control Mail in System Settings > Privacy & Security > Automation, then retry. Check Mail and any draft already opened; attachments may be incomplete.", comment: "")
        }
        return String(format: NSLocalizedString("Horos could not finish creating the Mail draft (error %ld). Check Mail and any draft already opened before retrying; attachments may be incomplete.", comment: ""), Int(code))
    }

    @objc(argumentsForSubject:filePaths:)
    public static func arguments(subject: String, filePaths: [String]) -> NSAppleEventDescriptor {
        let files = NSAppleEventDescriptor.list()
        let captions = NSAppleEventDescriptor.list()
        let comments = NSAppleEventDescriptor.list()
        for (index, path) in filePaths.enumerated() {
            files.insert(NSAppleEventDescriptor(string: path), at: index + 1)
            captions.insert(NSAppleEventDescriptor(string: ""), at: index + 1)
            comments.insert(NSAppleEventDescriptor(string: ""), at: index + 1)
        }
        let arguments = NSAppleEventDescriptor.list()
        arguments.insert(NSAppleEventDescriptor(string: subject), at: 1)
        // The compiled handler still receives this slot; keep it empty so no
        // recipient is ever supplied on the export path.
        arguments.insert(NSAppleEventDescriptor(string: ""), at: 2)
        arguments.insert(NSAppleEventDescriptor(int32: Int32(filePaths.count)), at: 3)
        arguments.insert(files, at: 4)
        arguments.insert(captions, at: 5)
        arguments.insert(comments, at: 6)
        arguments.insert(NSAppleEventDescriptor(string: "Cancel"), at: 7)
        return arguments
    }

    @objc(consentStatusAskingUser:)
    public static func systemConsent(askingUser: Bool) -> OSStatus {
        // Retain the synchronous selector for existing callers. The main
        // thread can only perform a bounded, non-prompting compatibility check;
        // interactive callers use the completion-based API below.
        if !Thread.isMainThread { return determineConsent(askingUser: askingUser) }
        return checkWithoutPrompt { determineConsent(askingUser: false) }
    }

    private static func determineConsent(askingUser: Bool) -> OSStatus {
        precondition(!Thread.isMainThread)
        let target = NSAppleEventDescriptor(bundleIdentifier: mailBundleIdentifier)
        guard let address = target.aeDesc else { return OSStatus(errAECorruptData) }
        return AEDeterminePermissionToAutomateTarget(
            address,
            AEEventClass(typeWildCard),
            AEEventID(typeWildCard),
            askingUser
        )
    }

    static func checkWithoutPrompt(timeout: DispatchTimeInterval = .seconds(2),
                                   using check: @escaping @Sendable () -> OSStatus) -> OSStatus {
        let result = Mutex<OSStatus?>(nil)
        let ready = DispatchSemaphore(value: 0)
        DispatchQueue.global(qos: .userInitiated).async {
            let status = check()
            result.withLock { $0 = status }
            ready.signal()
        }
        guard ready.wait(timeout: .now() + timeout) == .success else {
            return OSStatus(errAETimeout)
        }
        return result.withLock { $0! }
    }

    @objc(composeRecipientFreeDraftWithSubject:filePaths:completion:)
    @MainActor public static func compose(subject: String, filePaths: [String],
                                          completion: @escaping (String?) -> Void) {
        if let error = attachmentError(filePaths: filePaths) { completion(error); return }
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: mailBundleIdentifier) else {
            completion(message(errorInfo: [NSAppleScript.errorNumber: procNotFound], result: nil))
            return
        }
        // The permission API requires an already-running target. Launch Mail
        // without creating a message, then ask from a blocking dispatch worker.
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        NSWorkspace.shared.openApplication(at: url, configuration: configuration) { _, launchError in
            DispatchQueue.main.async {
                if let launchError { completion(launchError.localizedDescription); return }
                compose(subject: subject, filePaths: filePaths, scriptURL: nil,
                        using: { determineConsent(askingUser: true) }, completion: completion)
            }
        }
    }

    @MainActor static func compose(subject: String, filePaths: [String], scriptURL: URL?,
                                    using check: @escaping @Sendable () -> OSStatus,
                                    completion: @escaping (String?) -> Void) {
        guard !requestPending else {
            completion(NSLocalizedString("A Mail permission request is already pending. Respond to the macOS permission request before trying again.", comment: ""))
            return
        }
        if let error = attachmentError(filePaths: filePaths) { completion(error); return }
        requestPending = true
        DispatchQueue.global(qos: .userInitiated).async {
            let status = check()
            DispatchQueue.main.async {
                NSLog("Mail Automation consent returned: %d", status)
                // Only captured value-type paths cross the consent wait. The
                // script and completion stay on main, with no viewer/Core Data
                // access from the worker. Revalidate attachments after waiting.
                let error = compose(subject: subject, filePaths: filePaths,
                                    scriptURL: scriptURL, injectedConsent: NSNumber(value: status))
                requestPending = false
                completion(error)
            }
        }
    }

    private static func attachmentError(filePaths: [String]) -> String? {
        for path in filePaths where !FileManager.default.fileExists(atPath: path) {
            return NSLocalizedString("Horos could not prepare the Mail draft because an attachment is missing. Nothing was sent.", comment: "")
        }
        return nil
    }

    @objc(composeRecipientFreeDraftWithSubject:filePaths:)
    public static func compose(subject: String, filePaths: [String]) -> String? {
        compose(subject: subject, filePaths: filePaths, scriptURL: nil, injectedConsent: nil)
    }

    @objc(composeRecipientFreeDraftWithSubject:filePaths:scriptURL:consentStatus:)
    public static func compose(subject: String,
                               filePaths: [String],
                               scriptURL: URL?,
                               injectedConsent: NSNumber?) -> String? {
        if !Thread.isMainThread {
            var message: String?
            DispatchQueue.main.sync {
                message = compose(subject: subject, filePaths: filePaths, scriptURL: scriptURL, injectedConsent: injectedConsent)
            }
            return message
        }
        if let error = attachmentError(filePaths: filePaths) { return error }
        let status = injectedConsent?.int32Value ?? systemConsent(askingUser: false)
        if status != noErr {
            return message(errorInfo: [NSAppleScript.errorNumber: status], result: nil)
        }
        let url = scriptURL ?? Bundle.main.url(forResource: "Mail", withExtension: "scpt")
        var loadError: NSDictionary?
        guard let url, let script = NSAppleScript(contentsOf: url, error: &loadError), loadError == nil else {
            return message(errorInfo: nil, result: nil)
        }
        let arguments = arguments(subject: subject, filePaths: filePaths)
        let (result, error) = callHandler(script, name: handlerName, arguments: arguments)
        return message(errorInfo: error as? [AnyHashable: Any], result: result)
    }

    private static func callHandler(_ script: NSAppleScript,
                                    name: String,
                                    arguments: NSAppleEventDescriptor) -> (NSAppleEventDescriptor?, NSDictionary?) {
        var pid = Int32(ProcessInfo.processInfo.processIdentifier)
        let target = NSAppleEventDescriptor(
            descriptorType: DescType(typeKernelProcessID),
            bytes: &pid,
            length: MemoryLayout<Int32>.size
        )
        let event = NSAppleEventDescriptor(
            eventClass: subroutineEventClass,
            eventID: subroutineEventID,
            targetDescriptor: target,
            returnID: AEReturnID(kAutoGenerateReturnID),
            transactionID: AETransactionID(kAnyTransactionID)
        )
        event.setParam(NSAppleEventDescriptor(string: name), forKeyword: subroutineNameKeyword)
        event.setParam(arguments, forKeyword: AEKeyword(keyDirectObject))
        var error: NSDictionary?
        let result = script.executeAppleEvent(event, error: &error)
        return (result, error)
    }
}
