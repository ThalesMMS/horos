import Foundation

/// The image a study's archived SR - its annotations, its report, its windows state - refers to and takes its
/// patient data from (#651). Any image of any series used to be taken. Once the study held the app's own SRs, that
/// could be one of them: an SR with no SOP class for the reference, which was written unreadable and refused on
/// import, or a file rewritten at that moment, which left the SR without a patient and made a study of its own.
@objc(HorosArchivedSRReference)
public final class ArchivedSRReference: NSObject {
    private static let structuredReports = "1.2.840.10008.5.1.4.1.1.88."
    private static let encapsulatedDocuments = "1.2.840.10008.5.1.4.1.1.104."

    /// The first image, by instance number, of the first series, by series number and date, that holds images:
    /// with a SOP class that is not a structured report or an encapsulated document, and a SOP instance UID.
    /// nil when no series qualifies. `series` are objects with `seriesSOPClassUID`, `id`, `date` and `images`
    /// (each with `sopInstanceUID` and `instanceNumber`).
    @objc(imageInSeries:)
    public static func image(inSeries series: [Any]?) -> Any? {
        let candidates = (series ?? []).compactMap { $0 as? NSObject }.filter { item in
            guard let sopClass = item.value(forKey: "seriesSOPClassUID") as? String, !sopClass.isEmpty else { return false }
            return !sopClass.hasPrefix(structuredReports) && !sopClass.hasPrefix(encapsulatedDocuments)
        }
        let ordered = candidates.sorted { a, b in
            let numberA = (a.value(forKey: "id") as? NSNumber)?.intValue ?? Int.max
            let numberB = (b.value(forKey: "id") as? NSNumber)?.intValue ?? Int.max
            if numberA != numberB { return numberA < numberB }
            let dateA = a.value(forKey: "date") as? Date ?? .distantFuture
            let dateB = b.value(forKey: "date") as? Date ?? .distantFuture
            return dateA < dateB
        }
        for item in ordered {
            let images = (item.value(forKey: "images") as? NSSet)?.allObjects.compactMap { $0 as? NSObject } ?? []
            let usable = images.filter { ($0.value(forKey: "sopInstanceUID") as? String).map { !$0.isEmpty } ?? false }
            if let first = usable.min(by: { a, b in
                ((a.value(forKey: "instanceNumber") as? NSNumber)?.intValue ?? Int.max)
                    < ((b.value(forKey: "instanceNumber") as? NSNumber)?.intValue ?? Int.max)
            }) {
                return first
            }
        }
        return nil
    }
}
