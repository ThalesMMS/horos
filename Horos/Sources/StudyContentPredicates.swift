import Foundation

/// Smart-album criteria that ask what a study *contains* (#380 B).
///
/// A smart album is one predicate string against the study entity. Asking for
/// studies that carry regions of interest or segmentations is therefore a
/// clause over the study's own series, not a second database: legacy Horos and
/// OsiriX ROIs live in the study's `OsiriX ROI SR` series (series number 5002),
/// and segmentations of the shared #376 model are series of modality SEG. The
/// clause below is the only place those two facts are written down for the
/// album editor, so the editor, the count and the listing all ask the same
/// question.
@objc(HorosStudyContentPredicates)
public final class StudyContentPredicates: NSObject {
    /// The legacy ROI Structured Report series, as `DicomStudy.roiSRSeries`
    /// identifies it: series number 5002 named "OsiriX ROI SR".
    @objc public static let legacyROISeriesNumber = 5002
    @objc public static let legacyROISeriesName = "OsiriX ROI SR"

    /// Studies with at least one legacy ROI SR series.
    @objc public static let legacyROIFormat =
        "SUBQUERY(series, $s, $s.id == 5002 AND $s.name == \"OsiriX ROI SR\").@count > 0"

    /// Studies with at least one segmentation series.
    @objc public static let segmentationFormat =
        "SUBQUERY(series, $s, $s.modality ==[c] \"SEG\").@count > 0"

    /// Either of the two.
    @objc public static let roiOrSegmentationFormat =
        "SUBQUERY(series, $s, ($s.id == 5002 AND $s.name == \"OsiriX ROI SR\") OR $s.modality ==[c] \"SEG\").@count > 0"

    /// Every clause this type can add, so the editor can recognise its own.
    @objc public static let allFormats: [String] = [roiOrSegmentationFormat, legacyROIFormat, segmentationFormat]

    /// True when `predicateFormat` already carries `clause`.
    @objc public static func contains(_ clause: String, in predicateFormat: String?) -> Bool {
        guard let format = predicateFormat else { return false }
        return normalise(format).contains(normalise(clause))
    }

    /// `predicateFormat` with `clause` added, as a conjunction, once. An empty
    /// or absent predicate becomes the clause itself.
    @objc public static func adding(_ clause: String, to predicateFormat: String?) -> String {
        let trimmed = (predicateFormat ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty || normalise(trimmed) == normalise("TRUEPREDICATE") { return clause }
        if contains(clause, in: trimmed) { return trimmed }
        return "(\(trimmed)) AND \(clause)"
    }

    /// `predicateFormat` without `clause`, leaving the rest of the predicate —
    /// and its parentheses — as the user wrote it. An empty result means the
    /// album matches everything again.
    @objc public static func removing(_ clause: String, from predicateFormat: String?) -> String {
        guard var format = predicateFormat, contains(clause, in: format) else {
            return predicateFormat ?? ""
        }
        for pattern in ["(\(clause))", clause] {
            for joiner in [" AND ", " and ", " && "] {
                for candidate in [joiner + pattern, pattern + joiner] {
                    if let range = range(of: candidate, in: format) {
                        format.removeSubrange(range)
                        return tidy(format)
                    }
                }
            }
            if let range = range(of: pattern, in: format) {
                format.removeSubrange(range)
                return tidy(format)
            }
        }
        return tidy(format)
    }

    /// Whitespace-insensitive comparison: the editor and the stored album may
    /// differ only by spacing.
    static func normalise(_ text: String) -> String {
        text.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
    }

    static func range(of needle: String, in haystack: String) -> Range<String.Index>? {
        if let range = haystack.range(of: needle) { return range }
        // Retry ignoring how much whitespace the user typed.
        let normalisedHaystack = normalise(haystack)
        guard normalisedHaystack != haystack, normalisedHaystack.contains(normalise(needle)) else { return nil }
        return nil
    }

    static func tidy(_ format: String) -> String {
        var text = normalise(format)
        while text.hasPrefix("AND ") { text.removeFirst(4) }
        while text.hasSuffix(" AND") { text.removeLast(4) }
        text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        // A single pair of parentheses left around the whole thing is noise.
        if text.hasPrefix("("), text.hasSuffix(")") {
            var depth = 0
            var wrapsAll = true
            for (index, character) in text.enumerated() {
                if character == "(" { depth += 1 }
                if character == ")" {
                    depth -= 1
                    if depth == 0 && index != text.count - 1 { wrapsAll = false; break }
                }
            }
            if wrapsAll {
                var inner = text
                inner.removeFirst(); inner.removeLast()
                text = inner.trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return text
    }
}
