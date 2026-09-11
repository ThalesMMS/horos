import Foundation

/// The two spellings a DICOM keyword has had.
///
/// DICOM dropped the possessive from a family of names in 2011: `PatientsName`
/// became `PatientName`, `ReferringPhysiciansName` became
/// `ReferringPhysicianName`, and so on. The table the process compiles is still
/// the 2005 builtin (`Binaries/dcmtk-source/dcmdata/dcdictbi.cc`), which answers
/// to the old names. At launch the vendored `dicom.dic` is overlaid so the
/// modern names are present too, and a keyword is still looked up twice so a
/// caller that kept the possessive keeps working.
@objc(HorosDICOMKeyword)
public final class DICOMKeyword: NSObject {
    /// The words that gained or lost an `s` in that rename. The `s` sits between
    /// the word and the next capital, which is what makes this a rule rather
    /// than a list of every affected tag.
    static let possessives = ["Patient", "Physician"]

    /// The same keyword spelled the other way, or nil when it has only one
    /// spelling. `PatientName` <-> `PatientsName`,
    /// `ReferringPhysicianName` <-> `ReferringPhysiciansName`.
    @objc(otherSpellingFor:)
    public static func otherSpelling(for keyword: String) -> String? {
        for word in possessives {
            // Already possessive: drop the s, if a capital follows it.
            if let range = keyword.range(of: word + "s"), followedByCapital(keyword, after: range) {
                return keyword.replacingCharacters(in: range, with: word)
            }
        }
        for word in possessives {
            if let range = keyword.range(of: word), followedByCapital(keyword, after: range) {
                return keyword.replacingCharacters(in: range, with: word + "s")
            }
        }
        return nil
    }

    /// The written keyword, then the other 2011 spelling when there is one.
    /// `getDicomField:` tries them in this order so either side of the rename
    /// reaches the same tag.
    @objc(spellingsToTryFor:)
    public static func spellingsToTry(for keyword: String) -> [String] {
        if let other = otherSpelling(for: keyword) {
            return [keyword, other]
        }
        return [keyword]
    }

    static func followedByCapital(_ text: String, after range: Range<String.Index>) -> Bool {
        guard range.upperBound < text.endIndex else { return false }
        return text[range.upperBound].isUppercase
    }
}
