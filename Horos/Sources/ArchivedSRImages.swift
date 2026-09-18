import Foundation

/// A study keeps every SR the app archives for it - its annotations, its report, its windows state - and
/// reads back the most recent. An SR's date is its DICOM content date and time, to the second, so SRs
/// written within one second tie, and sorting by date alone returned one of them at random: three quick
/// edits could have the annotations SR of the first applied back over the last one, and the study's state
/// went back to what it was (#645). Within a second the SR stored later, under the higher number in the
/// database folder, is the more recent.
@objc(HorosArchivedSRImages)
public final class ArchivedSRImages: NSObject {
    /// `images` (objects with `date` and `pathNumber`) from the oldest to the most recent.
    @objc(sortedOldestFirst:)
    public static func sortedOldestFirst(_ images: [Any]?) -> [Any] {
        guard let images else { return [] }
        let keyed = images.enumerated().map { index, image -> (index: Int, date: Date, number: Int64, image: Any) in
            let object = image as? NSObject
            let date = object?.value(forKey: "date") as? Date ?? .distantPast
            let number = (object?.value(forKey: "pathNumber") as? NSNumber)?.int64Value ?? -1
            return (index, date, number, image)
        }
        return keyed.sorted { a, b in
            if a.date != b.date { return a.date < b.date }
            if a.number != b.number { return a.number < b.number }
            return a.index < b.index
        }.map(\.image)
    }
}
