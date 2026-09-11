import Foundation

/// Why a study that was asked for did not open.
///
/// `-[BrowserController displayStudy:object:command:]` is how every order from
/// outside the application arrives: an XML-RPC `DisplaySeries` or `DisplayStudy`,
/// a `horos://` link from a worklist, a message from a plugin. It begins by
/// selecting the study in the database list, and when that cannot be done it
/// returns `NO` - which every one of those callers discarded. The order was
/// answered with success, the caller's viewer never appeared, and nothing
/// anywhere said why. That is the difference between "the viewer is broken" and
/// "that study is not in this database".
///
/// These sentences go in the log beside the study, and the one a person is
/// waiting on - a link they clicked - is also shown to them.
@objc(HorosStudyNotOpenedReason)
public final class StudyNotOpenedReason: NSObject {
    private static func naming(_ text: String, _ studyInstanceUID: String?) -> String {
        guard let uid = studyInstanceUID?.trimmingCharacters(in: .whitespacesAndNewlines),
              !uid.isEmpty else { return text }
        return text + " (" + uid + ")"
    }

    /// No database is open. The browser has none while it is switching between
    /// databases, and an order that arrives in that moment cannot be served.
    @objc public static func reasonForNoDatabase() -> String {
        return NSLocalizedString("No database is open",
                                 comment: "why a study could not be opened")
    }

    /// The order named something that is not a study - or a study that has since
    /// been deleted, leaving nothing to select.
    @objc public static func reasonForNoStudy() -> String {
        return NSLocalizedString("The request did not name a study that still exists",
                                 comment: "why a study could not be opened")
    }

    /// The study object belongs to no store: it was deleted, or it came from a
    /// context that has been torn down. Following it would fault on nothing.
    @objc(reasonForStudyOutsideAnyDatabase:)
    public static func reasonForStudyOutsideAnyDatabase(_ studyInstanceUID: String?) -> String {
        return naming(NSLocalizedString("That study is no longer in any open database",
                                        comment: "why a study could not be opened"),
                      studyInstanceUID)
    }

    /// The study lives in another store and no `DicomDatabase` is known for it,
    /// so the browser cannot switch to it. A database that was unmounted or
    /// closed while its studies were still being referred to looks like this.
    @objc(reasonForUnknownDatabase:)
    public static func reasonForUnknownDatabase(_ studyInstanceUID: String?) -> String {
        return naming(NSLocalizedString("That study belongs to a database this window cannot open",
                                        comment: "why a study could not be opened"),
                      studyInstanceUID)
    }

    /// The study is in the database and is not in the list: it was added after
    /// the list was built and nothing has refreshed it, or an album, a search or
    /// a date filter is hiding it and showing the whole database did not bring
    /// it back. The viewer opens from the list, so this is where an import that
    /// arrived a moment ago stops.
    @objc(reasonForStudyNotListed:)
    public static func reasonForStudyNotListed(_ studyInstanceUID: String?) -> String {
        return naming(NSLocalizedString("That study is not in the database list",
                                        comment: "why a study could not be opened"),
                      studyInstanceUID)
    }

    /// Every study the order matched carries no series of images - a study of
    /// reports, of presentation states, of key-object notes. There is nothing
    /// for a 2D viewer to show.
    @objc(reasonForNoImageSeries:)
    public static func reasonForNoImageSeries(_ studyInstanceUID: String?) -> String {
        return naming(NSLocalizedString("That study carries no series of images",
                                        comment: "why a study could not be opened"),
                      studyInstanceUID)
    }

    /// Looking the study up in the list raised an exception - the list changed
    /// under the search, a property was not there. The exception itself is
    /// logged with its stack; this is what the caller waiting on a viewer is
    /// told, and it deliberately does not claim the study is missing.
    @objc public static func reasonForErrorWhileSelecting() -> String {
        return NSLocalizedString("Something went wrong looking for that study in the list",
                                 comment: "why a study could not be opened")
    }

    /// Written in front of a reason in the log, so a search for one word finds
    /// every refusal whatever the reason was.
    @objc public static func logPrefix() -> String {
        return "Study not opened: "
    }
}
