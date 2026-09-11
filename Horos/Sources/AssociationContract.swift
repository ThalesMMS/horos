import Foundation

/// The published association and indexing contract (#380 C), the one #383's
/// surgical-log import and timeline already consume.
///
/// It states, in one place and with a version, the rules every consumer may
/// rely on when it resolves a patient or a study in the local database and when
/// it waits for the database to have indexed something. It adds no storage and
/// no lookup of its own: `+[DicomFile patientUID:]` still composes the patient
/// key, `HorosPatientIdentity` still compares two of them, and the browser
/// still posts the notifications named here. What is new is that the rules are
/// written down, tested, and carry a version consumers can check against.
@objc(HorosAssociationContract)
public final class AssociationContract: NSObject {
    /// Raised when a rule below changes in a way a consumer must notice.
    @objc(contractVersion) public static let version = 1

    // MARK: Identity

    /// The patient key the database indexes by: patient name, patient ID and
    /// birth date, uppercased and joined by "-", each part included only when
    /// its preference says so (`UsePatientNameForUID`, `UsePatientIDForUID`,
    /// `UsePatientBirthDateForUID`, all on by default). Consumers must treat it
    /// as opaque and compare it whole.
    @objc public static let patientKeyDescription =
        "patientUID = uppercase(patientName)-uppercase(patientID)-birthDate(yyyyMMdd), each part per its preference"

    /// Study identity is the Study Instance UID, always. A study is never
    /// identified by description, date or accession number.
    @objc public static let studyKeyDescription = "studyInstanceUID"

    /// Names are never a merge key: two patients may share a name, and one
    /// patient may be recorded under two. A consumer that cannot tell two
    /// candidates apart must ask, not choose.
    @objc public static let mayMergeByNameSimilarity = false

    /// Comparisons of identity are case, diacritic and width insensitive, as
    /// the browser's own comparisons are.
    public static let comparisonOptions: String.CompareOptions = [.caseInsensitive, .diacriticInsensitive, .widthInsensitive]

    /// True when two patient keys denote the same patient under this contract.
    @objc(patientKey:matchesKey:)
    public static func patientKey(_ a: String?, matches b: String?) -> Bool {
        guard let a = a, let b = b, a.count > 1, b.count > 1 else { return false }
        return a.compare(b, options: comparisonOptions) == .orderedSame
    }

    /// The candidates a consumer must disambiguate: every distinct patient key
    /// among the rows it matched. More than one means it must ask.
    @objc(ambiguousPatientKeysAmong:)
    public static func ambiguousPatientKeys(among keys: [String]) -> [String] {
        var distinct: [String] = []
        for key in keys where !key.isEmpty {
            if !distinct.contains(where: { patientKey($0, matches: key) }) { distinct.append(key) }
        }
        return distinct.count > 1 ? distinct : []
    }

    // MARK: Indexing

    /// Posted after files are added to the database. A consumer that writes
    /// objects and then wants to see them indexed waits for this.
    @objc public static let didAddNotification = "OsirixAddToDBNotification"
    /// Posted when the database context changed under the consumer.
    @objc public static let didChangeContextNotification = "OsirixDicomDatabaseDidChangeContextNotification"
    /// Posted when whole studies arrive, which is when a comparative or
    /// timeline list has to be recomputed rather than only redrawn.
    @objc public static let didAddStudiesNotification = "OsirixAddNewStudiesDBNotification"

    /// Indexing is asynchronous: a consumer must not assume a file it wrote is
    /// in the database before the notification above.
    @objc public static let indexingIsAsynchronous = true

    /// Writing an object that already exists updates it in place; identity for
    /// that is the SOP Instance UID. A consumer that re-imports the same
    /// source must therefore be idempotent by SOP Instance UID.
    @objc public static let instanceKeyDescription = "sopInstanceUID"

    // MARK: Related studies

    /// How many related studies a search may return before it truncates, so a
    /// patient with a long history cannot make the browser fetch everything.
    /// Stored under `comparativeStudiesLimit`; zero or less means no limit.
    @objc public static let relatedStudiesLimitKey = "comparativeStudiesLimit"
    @objc public static let defaultRelatedStudiesLimit = 200

    @objc(relatedStudiesLimitIn:)
    public static func relatedStudiesLimit(in defaults: UserDefaults) -> Int {
        guard defaults.object(forKey: relatedStudiesLimitKey) != nil else { return defaultRelatedStudiesLimit }
        let stored = defaults.integer(forKey: relatedStudiesLimitKey)
        return stored > 0 ? stored : 0
    }

    /// A truncated list keeps the most recent studies: they are what a reader
    /// compares against. The caller sorts by date descending and takes the
    /// first `limit`.
    @objc public static let truncationKeepsMostRecent = true

    /// How long a related-studies result stays usable before it is searched
    /// again, in seconds. The browser already used this interval.
    @objc public static let relatedStudiesCacheSeconds = 180.0

    /// A one-line summary a consumer can log to record which contract it built
    /// against.
    @objc public static var summary: String {
        "Horos association contract v\(version): patient by \(patientKeyDescription); study by \(studyKeyDescription); "
        + "no merge by name; indexing asynchronous, announced by \(didAddNotification); "
        + "instances idempotent by \(instanceKeyDescription); related studies limited to \(defaultRelatedStudiesLimit) by default, "
        + "most recent first, cached \(Int(relatedStudiesCacheSeconds)) s."
    }
}
