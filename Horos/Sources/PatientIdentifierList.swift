import Foundation

/// The identifiers a query field names, when it names more than one.
///
/// People type several patient identifiers into the one field, separated by
/// commas, because that is what a list looks like. DICOM has no such thing: a
/// C-FIND identifier carries one value per key, and a comma is simply part of
/// the value — so the query matched a patient whose ID contains commas, which is
/// to say nothing at all, and the window came back empty with no explanation.
///
/// Splitting the field into the identifiers it names, and running one query per
/// identifier, is the only way to ask a conforming node this question. The
/// results are the union; each study carries its own patient identifier, so
/// nothing is lost by combining them.
@objc(HorosPatientIdentifierList)
public final class PatientIdentifierList: NSObject {
    /// A list this long is a mistake rather than a request; every entry is an
    /// association with the node.
    @objc public static let limit = 100

    /// The identifiers in a field value, in the order they were written, without
    /// repeats and without empty entries.
    ///
    /// A space is not a separator: identifiers in some systems contain them, and
    /// the field is a single identifier far more often than it is a list.
    @objc(identifiersInText:)
    public static func identifiers(in text: String?) -> [String] {
        guard let text = text, !text.isEmpty else { return [] }
        let separators = CharacterSet(charactersIn: ",;\n\r\t")
        var found: [String] = []
        for piece in text.components(separatedBy: separators) {
            let identifier = piece.trimmingCharacters(in: .whitespaces)
            if identifier.isEmpty || found.contains(identifier) {
                continue
            }
            found.append(identifier)
            if found.count == limit {
                break
            }
        }
        return found
    }

    /// Whether this field is a list, and so needs one query per entry.
    @objc(namesSeveralIdentifiers:)
    public static func namesSeveral(_ text: String?) -> Bool {
        return identifiers(in: text).count > 1
    }

    /// What was dropped, for the log: entries beyond the limit, and repeats.
    @objc(summaryForText:)
    public static func summary(forText text: String?) -> String {
        guard let text = text else { return "no identifiers" }
        let separators = CharacterSet(charactersIn: ",;\n\r\t")
        let written = text.components(separatedBy: separators)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        let kept = identifiers(in: text)
        var sentence = "\(kept.count) identifier\(kept.count == 1 ? "" : "s")"
        if written.count > kept.count {
            let repeated = written.count - kept.count
            sentence += ", \(repeated) repeated or beyond the limit of \(limit) ignored"
        }
        return sentence
    }
}
