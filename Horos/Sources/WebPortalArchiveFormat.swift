import Foundation

/// Which archive the Web Portal hands a client, and how it labels it.
///
/// The download has always been a plain zip made by `/usr/bin/zip`; what was
/// application specific was the label. WADO always answered
/// `application/osirixzip` with an `.osirixzip` name, and the `/zip` route sent
/// no content type and no file name at all, so a common zip client had a file it
/// did not recognise and a name taken from the URL.
///
/// The legacy label is what tells Horos on the other end to import the archive
/// into its database, so it stays available and stays the default for the links
/// a Mac client follows.
@objc(HorosWebPortalArchiveFormat)
public final class WebPortalArchiveFormat: NSObject {
    /// `osirixzip`, which Horos imports, or `zip`, which every client opens.
    @objc public let pathExtension: String
    @objc public let mimeType: String
    /// True for the application specific label.
    @objc public let isLegacy: Bool

    private init(pathExtension: String, mimeType: String, isLegacy: Bool) {
        self.pathExtension = pathExtension
        self.mimeType = mimeType
        self.isLegacy = isLegacy
        super.init()
    }

    @objc public static let standard = WebPortalArchiveFormat(
        pathExtension: "zip", mimeType: "application/zip", isLegacy: false)
    @objc public static let legacy = WebPortalArchiveFormat(
        pathExtension: "osirixzip", mimeType: "application/osirixzip", isLegacy: true)

    /// Decides from what the request already carries.
    ///
    /// The requested path settles it when it names one — those links are what
    /// the portal's own pages generate. Otherwise an explicit `archive`
    /// parameter settles it. With neither, which is the WADO case, a macOS
    /// client keeps the legacy archive it has always been sent and everyone
    /// else gets the standard one.
    @objc(formatForRequestedPath:parameters:clientIsMacOS:)
    public static func format(forRequestedPath path: String?,
                              parameters: [String: Any]?,
                              clientIsMacOS: Bool) -> WebPortalArchiveFormat {
        if let path = path?.lowercased() {
            if path.hasSuffix(".osirixzip") { return legacy }
            if path.hasSuffix(".zip") { return standard }
        }
        switch (parameters?["archive"] as? String)?.lowercased() {
        case "osirixzip", "legacy": return legacy
        case "zip", "standard": return standard
        default: return clientIsMacOS ? legacy : standard
        }
    }

    /// The name to save under, without a path and with the right extension.
    ///
    /// Anything that would let the name escape its header or its directory is
    /// removed: separators, quotes, control characters. An empty result falls
    /// back to a fixed name rather than producing a file called ".zip".
    @objc(fileNameForStudyName:)
    public func fileName(forStudyName studyName: String?) -> String {
        var name = studyName ?? ""
        name = name.components(separatedBy: CharacterSet(charactersIn: "/\\:\"")).joined(separator: " ")
        name = name.components(separatedBy: .controlCharacters).joined(separator: " ")
        name = name.split(separator: " ", omittingEmptySubsequences: true).joined(separator: " ")
        // A leading dot hides the file, and a leading run of them is what is
        // left of a relative path once the separators are gone.
        name = String(name.drop { $0 == "." || $0 == " " })
        name = name.trimmingCharacters(in: .whitespaces)
        if name.isEmpty { name = "Horos" }
        return "\(name).\(pathExtension)"
    }

    /// A Content-Disposition value for that name.
    ///
    /// A study name is patient text and is regularly not ASCII, so the quoted
    /// `filename` carries a transliterated form for clients that read only that,
    /// and `filename*` carries the real one, per RFC 6266.
    @objc(contentDispositionForStudyName:)
    public func contentDisposition(forStudyName studyName: String?) -> String {
        let name = fileName(forStudyName: studyName)
        let ascii = asciiFallback(for: name)
        var disposition = "attachment; filename=\"\(ascii)\""
        if name != ascii {
            let allowed = CharacterSet(charactersIn:
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
            if let encoded = name.addingPercentEncoding(withAllowedCharacters: allowed) {
                disposition += "; filename*=UTF-8''\(encoded)"
            }
        }
        return disposition
    }

    private func asciiFallback(for name: String) -> String {
        let folded = name.folding(options: [.diacriticInsensitive], locale: Locale(identifier: "en_US_POSIX"))
        let scalars = folded.unicodeScalars.map { $0.isASCII && $0.value >= 0x20 && $0 != "\"" ? Character($0) : "_" }
        let ascii = String(scalars)
        return ascii.isEmpty ? "Horos.\(pathExtension)" : ascii
    }
}
