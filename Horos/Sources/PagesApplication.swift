import AppKit
import UniformTypeIdentifiers

/// Where Pages is, when it is anywhere.
///
/// Horos asked for the bundle identifier `com.apple.iWork.Pages`, which is what
/// Pages '09 answered to. Pages 15.3.1, installed and signed by Apple, answers to
/// `com.apple.Pages`, and measured on a machine with it installed:
///
///     com.apple.iWork.Pages: nil
///     com.apple.Pages: /Applications/Pages.app
///
/// so the report generator said "Pages is not installed or could not be located"
/// with Pages sitting in the Applications folder. Both identifiers are asked for
/// now, and after them the application registered to open a Pages document,
/// which is the question that actually matters and does not have to be revisited
/// the next time the identifier changes.
@objc(HorosPagesApplication)
public final class PagesApplication: NSObject {

    /// The identifiers Pages has used, newest last so the older one still wins
    /// where both are installed - a Pages '09 template needs Pages '09.
    private static let identifiers = ["com.apple.iWork.Pages", "com.apple.Pages"]

    /// The document type a Pages file is, which is how the application is found
    /// when it answers to neither identifier.
    private static let documentType = "com.apple.iwork.pages.pages"

    @objc public static func url() -> URL? {
        let workspace = NSWorkspace.shared
        for identifier in identifiers {
            if let url = workspace.urlForApplication(withBundleIdentifier: identifier) {
                return url
            }
        }
        // Asking by document type needs macOS 12; below it the two identifiers
        // above are all there is, which is what every Pages before then used.
        guard #available(macOS 12.0, *),
              let type = UTType(documentType),
              let url = workspace.urlForApplication(toOpen: type) else { return nil }
        // Only Apple's own: everything Horos does with a Pages file afterwards -
        // the index.xml of a '09 template, the AppleScript it sends - is Pages
        // and nothing else, and handing that to another editor that merely
        // claims the document type would fail in a way nobody could read.
        guard let bundle = Bundle(url: url),
              let identifier = bundle.bundleIdentifier,
              identifier.hasPrefix("com.apple.") else { return nil }
        return url
    }

    /// Its Info.plist, which is where the version that decides where templates
    /// live is read from.
    @objc public static func information() -> [String: Any]? {
        guard let url = url() else { return nil }
        return Bundle(url: url)?.infoDictionary
    }
}
