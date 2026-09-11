import Foundation

/// Studies out to a spreadsheet, with the columns somebody asked for.
///
/// The database list already exported its own columns, tab separated, with no
/// escaping at all: a study description holding a tab moved every field after it
/// into the wrong column, and one holding a carriage return split the row in two.
/// This writes the format that survives that - RFC 4180 - and takes its columns
/// from DICOM rather than from what the table happens to be showing.
@objc(HorosStudyMetadataExport)
public final class StudyMetadataExport: NSObject {
    /// The columns most people want, and a starting point somebody can edit.
    @objc public static let suggestedColumns = [
        "PatientName", "PatientID", "PatientBirthDate", "PatientSex",
        "StudyDate", "StudyTime", "AccessionNumber", "StudyDescription",
        "Modality", "InstitutionName", "StudyInstanceUID",
    ]

    /// One specification per line: a DICOM keyword (`PatientName`) or a tag
    /// written `(0010,0010)`. Blank lines and `#` comments are dropped, and a
    /// repeated column is kept once - a spreadsheet with the same header twice
    /// is a spreadsheet nobody can read back.
    @objc(columnsFromText:)
    public static func columns(fromText text: String) -> [String] {
        var seen = Set<String>()
        var out: [String] = []
        for line in text.components(separatedBy: .newlines) {
            var spec = line
            if let hash = spec.firstIndex(of: "#") { spec = String(spec[spec.startIndex ..< hash]) }
            spec = spec.trimmingCharacters(in: .whitespaces)
            guard !spec.isEmpty, !seen.contains(spec) else { continue }
            seen.insert(spec)
            out.append(spec)
        }
        return out
    }

    /// One field of a CSV row. A value that holds a comma, a quote, a carriage
    /// return or a line feed is quoted, and a quote inside it is doubled.
    @objc(escapedField:)
    public static func escaped(_ field: String?) -> String {
        let value = field ?? ""
        let needsQuoting = value.contains(",") || value.contains("\"")
            || value.contains("\r") || value.contains("\n")
        guard needsQuoting else { return value }
        return "\"" + value.replacingOccurrences(of: "\"", with: "\"\"") + "\""
    }

    /// The whole file, CRLF between records as the format says.
    @objc(csvFromRows:)
    public static func csv(fromRows rows: [[String]]) -> String {
        rows.map { $0.map { escaped($0) }.joined(separator: ",") }.joined(separator: "\r\n")
            + (rows.isEmpty ? "" : "\r\n")
    }

    /// UTF-8 with the byte order mark, because a spreadsheet opening a CSV
    /// without one reads the accents as whatever its locale happens to be.
    @objc(dataForCSV:)
    public static func data(forCSV text: String) -> Data {
        Data([0xEF, 0xBB, 0xBF]) + Data(text.utf8)
    }

    /// The header row: the specifications as written, plus the column that says
    /// which fields a study did not have.
    @objc public static let missingHeader = "Missing"

    @objc(headerRowForColumns:)
    public static func headerRow(columns: [String]) -> [String] {
        columns + [missingHeader]
    }

    /// One study's row. `values` holds only the fields the study actually has,
    /// so an absent field is an empty cell *and* a mention in the last column -
    /// an empty cell on its own cannot be told apart from a field that is there
    /// and empty, which DICOM allows.
    @objc(rowForColumns:values:)
    public static func row(columns: [String], values: [String: String]) -> [String] {
        var row: [String] = []
        var missing: [String] = []
        for column in columns {
            if let value = values[column] {
                row.append(cleaned(value))
            } else {
                row.append("")
                missing.append(column)
            }
        }
        row.append(missing.joined(separator: " "))
        return row
    }

    /// DICOM pads with spaces and separates multiple values with a backslash;
    /// neither belongs in a spreadsheet cell as it stands.
    static func cleaned(_ value: String) -> String {
        value.replacingOccurrences(of: "\\", with: "; ")
            .trimmingCharacters(in: CharacterSet(charactersIn: " \0"))
    }
}
