import AppKit
import Darwin
import Foundation

/// What to write, and what to tell the user, when a listen socket cannot bind.
///
/// The DICOM listener, the XML-RPC interface, the web portal and Bonjour
/// database sharing use OsiriX's default ports. A bind that fails used to leave a CFSocket errno in the log
/// with no service name and no port, or - for the web portal - a sentence that
/// never said which port. XML-RPC and DICOM said nothing to the person who
/// turned them on.
@objc(HorosListenBindFailure)
public final class ListenBindFailure: NSObject {
    @objc public static let webPortalService = "web portal"
    @objc public static let xmlrpcService = "XML-RPC"
    @objc public static let dicomService = "DICOM listen"
    @objc public static let databaseSharingService = "database sharing"

    private static let lock = NSLock()
    private static var shown = Set<String>()

    @objc(translatedErrno:)
    public static func translatedErrno(_ code: Int32) -> String {
        guard code != 0 else { return "unknown error" }
        return String(cString: strerror(code))
    }

    // errno: is a C macro; Horos-Swift.h is included from .mm files.
    @objc(logLineForService:port:errnoCode:)
    public static func logLine(service: String, port: Int, errno code: Int32) -> String {
        let reason = translatedErrno(code)
        return "Cannot start \(service) on port \(port): \(reason) (errno \(code))"
    }

    /// The historical web-portal sentence, with the port it tried inserted
    /// after the word "port" so translations of that sentence stay intact.
    @objc(webPortalUserMessageForPort:)
    public static func webPortalUserMessage(port: Int) -> String {
        let base = NSLocalizedString(
            "Cannot start Web Server. TCP/IP port is probably already used by another process.",
            comment: "web portal bind failure")
        if let range = base.range(of: "port") {
            var result = base
            result.replaceSubrange(range, with: "port \(port)")
            return result
        }
        return base + " (\(port))"
    }

    @objc(userMessageForService:port:errnoCode:)
    public static func userMessage(service: String, port: Int, errno code: Int32) -> String {
        if service == webPortalService {
            return webPortalUserMessage(port: port)
        }
        return String(format: NSLocalizedString(
            "Cannot start %@. TCP/IP port %d is probably already used by another process (%@).",
            comment: "listen bind failure"), service, port, translatedErrno(code))
    }

    /// True the first time this service and port failed in this process.
    @objc(consumeUserNoticeForService:port:)
    public static func consumeUserNotice(service: String, port: Int) -> Bool {
        let key = service + "#" + String(port)
        lock.lock()
        defer { lock.unlock() }
        if shown.contains(key) { return false }
        shown.insert(key)
        return true
    }

    @objc public static func resetUserNoticesForTests() {
        lock.lock()
        shown.removeAll()
        lock.unlock()
    }

    /// A sheet, once a window exists. Never `runModal`, and never from the
    /// thread that was trying to listen: startup must keep going.
    @objc(presentUserNotice:)
    public static func presentUserNotice(_ message: String) {
        DispatchQueue.main.async {
            presentOnMain(message, attemptsLeft: 8)
        }
    }

    private static func presentOnMain(_ message: String, attemptsLeft: Int) {
        let alert = NSAlert()
        alert.messageText = NSLocalizedString("Listener Error", comment: "listen bind failure title")
        alert.informativeText = message
        alert.addButton(withTitle: NSLocalizedString("OK", comment: ""))
        if let window = NSApp.mainWindow ?? NSApp.windows.first(where: { $0.isVisible }) {
            alert.beginSheetModal(for: window, completionHandler: nil)
            return
        }
        guard attemptsLeft > 0 else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
            presentOnMain(message, attemptsLeft: attemptsLeft - 1)
        }
    }
}
