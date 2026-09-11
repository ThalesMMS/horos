import ApplicationServices
import AppKit
import Foundation
import Synchronization

/// Check consent before opening any of the merge's private documents. Opening
/// a file is allowed without Automation access, but reading its name is not.
@objc(HorosWordReportAutomation)
public final class WordReportAutomation: NSObject {
    @MainActor private static var requestPending = false

    // AEDeterminePermissionToAutomateTarget can wait indefinitely for the
    // system consent panel. Never call it on the main thread (AppleEvents.h).
    private static func determineConsent(askingUser: Bool) -> OSStatus {
        precondition(!Thread.isMainThread)
        let target = NSAppleEventDescriptor(bundleIdentifier: "com.microsoft.Word")
        guard let address = target.aeDesc else {
            return OSStatus(errAECorruptData)
        }
        return AEDeterminePermissionToAutomateTarget(
            address, AEEventClass(typeWildCard), AEEventID(typeWildCard), askingUser
        )
    }

    /// The native UI asks asynchronously, then rechecks before opening files.
    /// Keep the legacy synchronous Reports API usable with already-granted
    /// consent, but do not make it wait for a user decision or pump a nested
    /// run loop that could change its selected study/database underneath it.
    @objc(consentErrorWithoutPrompt)
    public static func consentErrorWithoutPrompt() -> NSError? {
        checkWithoutPrompt { determineConsent(askingUser: false) }
    }

    static func checkWithoutPrompt(timeout: DispatchTimeInterval = .seconds(2),
                                   using check: @escaping @Sendable () -> OSStatus) -> NSError? {
        let result = Mutex<OSStatus?>(nil)
        let ready = DispatchSemaphore(value: 0)
        DispatchQueue.global(qos: .userInitiated).async {
            let status = check()
            result.withLock { $0 = status }
            ready.signal()
        }
        guard ready.wait(timeout: .now() + timeout) == .success else {
            return error(forStatus: OSStatus(errAETimeout))
        }
        return error(forStatus: result.withLock { $0! })
    }

    @objc(requestConsentWithCompletion:)
    @MainActor public static func requestConsent(completion: @escaping (NSError?) -> Void) {
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.microsoft.Word") else {
            completion(error(forStatus: OSStatus(procNotFound)))
            return
        }
        // The permission API only accepts an already-running target. Launch
        // Word without opening any private report/template document first.
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        NSWorkspace.shared.openApplication(at: url, configuration: configuration) { _, launchError in
            DispatchQueue.main.async {
                if let launchError { completion(launchError as NSError); return }
                requestConsent(using: { determineConsent(askingUser: true) }, completion: completion)
            }
        }
    }

    @MainActor static func requestConsent(using check: @escaping @Sendable () -> OSStatus,
                                          completion: @escaping (NSError?) -> Void) {
        guard !requestPending else {
            completion(NSError(domain: "HorosWordAutomation", code: 1, userInfo: [
                NSLocalizedDescriptionKey: NSLocalizedString("A Word permission request is already pending. Respond to the macOS permission request before trying again.", comment: "")
            ]))
            return
        }
        requestPending = true
        // This blocking C API belongs on a dispatch worker, not Swift's
        // cooperative executor. Only status crosses back; study objects and
        // the completion handler are accessed exclusively on the main thread.
        DispatchQueue.global(qos: .userInitiated).async {
            let status = check()
            DispatchQueue.main.async {
                requestPending = false
                NSLog("Word Automation consent returned: %d", status)
                completion(error(forStatus: status))
            }
        }
    }

    public static func error(forStatus status: OSStatus) -> NSError? {
        guard status != noErr else { return nil }
        let recovery: String
        if status == -1743 || status == -1744 || status == -1712 {
            recovery = NSLocalizedString("Allow Horos to control Microsoft Word in System Settings > Privacy & Security > Automation, then retry. No report document was opened or changed.", comment: "")
        } else {
            recovery = NSLocalizedString("Check that Microsoft Word is available, then retry. No report document was opened or changed.", comment: "")
        }
        return NSError(domain: "HorosWordAutomation", code: Int(status), userInfo: [
            NSLocalizedDescriptionKey: String(format: NSLocalizedString("Word Automation is unavailable (error %ld). %@", comment: ""), Int(status), recovery)
        ])
    }
}
