import Foundation

/// What came back from a URL, and what became of it.
///
/// "Import URL…" wrote whatever the server answered into the database's own file
/// folder as a `.dcm`, whatever it was, and reported success as long as some
/// bytes had arrived. Measured against a local server: a DICOM object landed and
/// was indexed; a zip served without a file extension became a `.dcm` holding a
/// zip, in the folder the database keeps its images, expanded by nothing and
/// indexed by nothing; and an HTML sign-in page - which is what a proxy answers
/// with a 200 - became a 76-byte `.dcm` beside it. Both were reported as
/// successful downloads.
@objc(HorosURLImportReport)
public final class URLImportReport: NSObject {

    private var indexed: [String] = []
    private var expanded: [String] = []
    private var refused: [(String, String)] = []
    private var failed: [(String, String)] = []

    /// The extension the content itself asks for, whatever the URL was called.
    ///
    /// A URL path carries no reliable extension - the ones this exists for have
    /// none at all - so the first bytes decide. `dcm` for a DICOM object, `zip`
    /// for an archive the importer knows how to expand, and nothing for anything
    /// else, which is how it reaches the importer's own answer for a file it
    /// cannot read rather than being disguised as an image.
    @objc(fileExtensionForPayload:)
    public class func fileExtension(forPayload data: Data) -> String {
        if data.count > 132 {
            let magic = data.subdata(in: 128..<132)
            if magic == Data("DICM".utf8) { return "dcm" }
        }
        if data.count >= 4, data.prefix(4) == Data([0x50, 0x4B, 0x03, 0x04]) { return "zip" }
        return ""
    }

    @objc(recordIndexedURL:)
    public func recordIndexed(url: String) { indexed.append(url) }

    /// Handed to the import folder to be expanded there - an archive gets its own
    /// verdict from the importer once it has been.
    @objc(recordExpandedURL:)
    public func recordExpanded(url: String) { expanded.append(url) }

    /// Downloaded, and not something this database can take.
    @objc(recordRefusedURL:reason:)
    public func recordRefused(url: String, reason: String) { refused.append((url, reason)) }

    /// Not downloaded at all.
    @objc(recordFailedURL:reason:)
    public func recordFailed(url: String, reason: String) { failed.append((url, reason)) }

    @objc public var everythingArrived: Bool {
        return refused.isEmpty && failed.isEmpty
    }

    /// One sentence for the alert, naming what went wrong rather than only that
    /// something did.
    @objc public var summary: String {
        var parts: [String] = []
        if !indexed.isEmpty {
            parts.append("\(indexed.count) added to the database")
        }
        if !expanded.isEmpty {
            parts.append("\(expanded.count) handed to the import folder to be expanded")
        }
        for (url, reason) in failed {
            parts.append("\(short(url)) could not be downloaded: \(reason)")
        }
        for (url, reason) in refused {
            parts.append("\(short(url)) is not something this database can take: \(reason)")
        }
        return parts.isEmpty ? "nothing was downloaded" : parts.joined(separator: "\n")
    }

    private func short(_ url: String) -> String {
        guard let components = URLComponents(string: url), let host = components.host else { return url }
        return components.path.isEmpty ? host : host + components.path
    }
}
