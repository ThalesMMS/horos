import Foundation

/// A list of patients read from an image - an outpatient schedule, a clinical
/// system's screen, a spreadsheet - turned into the studies of an album (#703).
///
/// This file is the part that decides, and has no AppKit, Vision or database in
/// it: the lines the text recognition produced go in, the entries of the list
/// come out; an entry and the local studies the database found for it go in,
/// which of them belong to the patient, and what the user must look at, come
/// out. The window and the recognition live in PatientListAlbumWindow.swift,
/// the database and the Query/Retrieve in BrowserController.
///
/// Nothing here writes a name or an identifier anywhere: the only record of a
/// list is the album the user chooses to create.

/// One patient of the list.
@objc(HorosPatientListEntry)
public final class PatientListEntry: NSObject {
    @objc public var name: String
    @objc public var identifier: String?
    /// Years, or -1 when the list does not say.
    @objc public var age: Int = -1
    /// "M", "F", or nil.
    @objc public var sex: String?
    /// The lowest recognition confidence of the lines that made the entry, 0...1.
    @objc public var confidence: Double = 1

    @objc public init(name: String, identifier: String?) {
        self.name = name
        self.identifier = identifier
    }
}

/// How the list writes an identifier, an age and a sex, and which lines are
/// headings. Every part has a default for Portuguese and English lists and can
/// be replaced in the preferences:
///
/// - `PatientListIdentifierPattern`: a regular expression whose first capture
///   group is the identifier. The default wants a label (ID, MRN, Prontuário,
///   Registro, ULI, Nº...) so that a number that is not an identifier - a
///   room, a time, a phone - is not taken for one.
/// - `PatientListIgnoredLines`: lines that are headings, compared normalised.
@objc(HorosPatientListFormat)
public final class PatientListFormat: NSObject {
    static let defaultIdentifierPattern =
        #"(?i)(?:\b(?:patient\s*id|id|mrn|uli|prontu[aá]rio|registro|reg|rg|n[º°o])\b\.?\s*[:#]?\s*)([A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?)"#
    static let defaultIgnoredLines = ["patient", "patients", "name", "names", "paciente", "pacientes", "nome", "nomes",
                                      "agenda", "schedule", "appointments", "consultas", "clinic", "clinica",
                                      "ambulatorio", "lista", "list", "patient list", "lista de pacientes"]

    let identifier: NSRegularExpression
    let ignored: Set<String>
    /// A line all of whose words are heading words ("Agenda - Ambulatório") is a heading too.
    let headingWords: Set<String>
    /// Set when the preference held an expression that cannot be used; the default is used instead.
    @objc public private(set) var problem: String?

    @objc public init(identifierPattern: String?, ignoredLines: [String]?) {
        var chosen: NSRegularExpression?
        if let pattern = identifierPattern, !pattern.isEmpty {
            if let expression = try? NSRegularExpression(pattern: pattern), expression.numberOfCaptureGroups >= 1 {
                chosen = expression
            } else {
                problem = NSLocalizedString("The identifier pattern in the preferences is not a regular expression with a capture group; the default is used.",
                                            comment: "Patient list import")
            }
        }
        identifier = chosen ?? (try! NSRegularExpression(pattern: Self.defaultIdentifierPattern))
        ignored = Set((ignoredLines ?? Self.defaultIgnoredLines).map(PatientListMatching.key))
        headingWords = Set(ignored.flatMap { $0.components(separatedBy: " ") })
    }

    func isHeading(_ text: String) -> Bool {
        let key = PatientListMatching.key(text)
        if ignored.contains(key) { return true }
        let words = key.components(separatedBy: " ").filter { !$0.isEmpty }
        return !words.isEmpty && words.allSatisfy(headingWords.contains)
    }

    /// The format the preferences describe.
    @objc public static func fromDefaults() -> PatientListFormat {
        let defaults = UserDefaults.standard
        return PatientListFormat(identifierPattern: defaults.string(forKey: "PatientListIdentifierPattern"),
                                 ignoredLines: defaults.stringArray(forKey: "PatientListIgnoredLines"))
    }
}

/// Lines of recognised text to entries.
@objc(HorosPatientListParser)
public final class PatientListParser: NSObject {
    static let numbering = try! NSRegularExpression(pattern: #"^\s*\d{1,3}\s*[.)\]:-]\s*"#)
    static let age = try! NSRegularExpression(pattern:
        #"(?i)(?<![\w/])(\d{1,3})\s*(?:y\.?\s*o\.?|yrs?\.?|years?(?:\s+old)?|anos?|a\.)(?:\s*(?:[/,;-]|\s)\s*(m|f|male|female|masc(?:ulino)?|fem(?:inino)?)\b\.?)?"#)
    static let labelledSex = try! NSRegularExpression(pattern:
        #"(?i)\bsex[o]?\s*[:=]\s*(m|f|male|female|masc(?:ulino)?|fem(?:inino)?)\b\.?"#)
    static let nameLabel = try! NSRegularExpression(pattern: #"(?i)^\s*(?:nome|name|paciente|patient)\s*:\s*"#)
    static let separators = CharacterSet(charactersIn: " \t-–—|,;:•·/()[]")

    /// `confidences[i]` belongs to `lines[i]`; missing ones count as 1.
    @objc public static func entries(lines: [String], confidences: [NSNumber], format: PatientListFormat) -> [PatientListEntry] {
        var entries: [PatientListEntry] = []
        for (index, raw) in lines.enumerated() {
            let confidence = index < confidences.count ? confidences[index].doubleValue : 1
            var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if text.isEmpty { continue }
            text = replacing(numbering, in: text, with: "")
            if format.isHeading(text) { continue }

            var identifier: String?
            if let match = format.identifier.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
               let range = Range(match.range(at: 1), in: text), let whole = Range(match.range, in: text) {
                identifier = String(text[range])
                text.replaceSubrange(whole, with: " ")
            }
            var age = -1
            var sex: String?
            if let match = Self.age.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
               let whole = Range(match.range, in: text) {
                if let years = Range(match.range(at: 1), in: text) { age = Int(text[years]) ?? -1 }
                if let s = Range(match.range(at: 2), in: text) { sex = normalisedSex(String(text[s])) }
                text.replaceSubrange(whole, with: " ")
            }
            if let match = labelledSex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
               let whole = Range(match.range, in: text) {
                if let s = Range(match.range(at: 1), in: text) { sex = normalisedSex(String(text[s])) }
                text.replaceSubrange(whole, with: " ")
            }
            text = replacing(nameLabel, in: text, with: "")
            let name = text.trimmingCharacters(in: separators)
                .components(separatedBy: .whitespaces).filter { !$0.isEmpty }.joined(separator: " ")

            if isName(name) && !format.isHeading(name) {
                let entry = PatientListEntry(name: name, identifier: identifier)
                entry.age = age; entry.sex = sex; entry.confidence = confidence
                entries.append(entry)
            } else if let last = entries.last, name.rangeOfCharacter(from: .letters) == nil || !isName(name) {
                // An identifier, an age or a sex on the line after the name belongs to that name.
                if identifier != nil || age >= 0 || sex != nil {
                    if last.identifier == nil, let identifier { last.identifier = identifier }
                    if last.age < 0 { last.age = age }
                    if last.sex == nil { last.sex = sex }
                    last.confidence = min(last.confidence, confidence)
                }
            }
        }
        return entries
    }

    /// Two words or more, of letters: no digits, which a name never has.
    static func isName(_ text: String) -> Bool {
        guard text.rangeOfCharacter(from: .decimalDigits) == nil else { return false }
        let words = text.components(separatedBy: CharacterSet(charactersIn: " ,^"))
            .filter { $0.rangeOfCharacter(from: .letters) != nil }
        return words.count >= 2
    }

    static func normalisedSex(_ text: String) -> String? {
        switch text.lowercased().first { case "m": return "M"; case "f": return "F"; default: return nil }
    }

    static func replacing(_ expression: NSRegularExpression, in text: String, with replacement: String) -> String {
        expression.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: replacement)
    }
}

/// Which local studies belong to an entry, and what the user must check.
@objc(HorosPatientListMatching)
public final class PatientListMatching: NSObject {
    /// Upper case, no accents, `^ , . -` as spaces, single spaces.
    @objc public static func key(_ text: String) -> String {
        let folded = text.folding(options: [.diacriticInsensitive, .caseInsensitive, .widthInsensitive], locale: nil).uppercased()
        let spaced = folded.map { "^,.-_'’".contains($0) ? " " : $0 }
        return String(spaced).components(separatedBy: .whitespaces).filter { !$0.isEmpty }.joined(separator: " ")
    }

    /// Particles a list writes and a DICOM name often leaves out, or the other way round.
    static let particles: Set<String> = ["DA", "DE", "DO", "DAS", "DOS", "E", "DI", "DEL", "DELLA", "VAN", "VON", "DER", "LA", "LE", "Y"]

    /// The words of a name that identify it: initials and particles dropped, order ignored.
    static func words(_ name: String) -> Set<String> {
        Set(key(name).components(separatedBy: " ").filter { $0.count > 1 && !particles.contains($0) })
    }

    /// The words to look a name up with, for the database's own search.
    @objc public static func searchWords(_ name: String) -> [String] {
        words(name).sorted()
    }

    /// `candidates` are the local studies the database found, as dictionaries
    /// with `patientUID`, `patientID`, `name`, and optionally `dateOfBirth`
    /// (NSDate) and `sex`. Returns the indexes of the candidates that belong to
    /// the entry's patient, and the reasons to look before including them.
    ///
    /// - An identifier equal to a candidate's patient ID decides: every study
    ///   of that patient ID, whatever the name, which is then checked.
    /// - An identifier that no candidate has is not replaced by a name match:
    ///   the name candidates are offered, and the entry is not included
    ///   without confirmation.
    /// - Without an identifier, the name must have the same words as the
    ///   patient's (order and initials aside); several patients of that name
    ///   are never joined, and the entry needs confirmation.
    @objc public static func decide(entry: PatientListEntry, candidates: [[String: Any]], now: Date) -> PatientListDecision {
        let decision = PatientListDecision()
        if entry.confidence < 0.9 {
            decision.warnings.append(NSLocalizedString("Text recognition was unsure of this line.", comment: "Patient list import"))
        }
        func id(_ c: [String: Any]) -> String { key((c["patientID"] as? String) ?? "") }
        var chosen: [Int] = []
        if let identifier = entry.identifier.map(key), !identifier.isEmpty {
            chosen = candidates.indices.filter { id(candidates[$0]) == identifier }
            if chosen.isEmpty {
                decision.warnings.append(NSLocalizedString("No local study has this identifier.", comment: "Patient list import"))
            } else {
                decision.matchedByIdentifier = true
                let names = Set(chosen.map { words((candidates[$0]["name"] as? String) ?? "") })
                if !names.contains(words(entry.name)) {
                    decision.warnings.append(NSLocalizedString("The name differs from the one stored for this identifier.", comment: "Patient list import"))
                }
            }
        }
        if chosen.isEmpty {
            let wanted = words(entry.name)
            let byName = candidates.indices.filter { !wanted.isEmpty && words((candidates[$0]["name"] as? String) ?? "") == wanted }
            let patients = Set(byName.map { id(candidates[$0]) + "|" + ((candidates[$0]["patientUID"] as? String) ?? "") })
            if patients.count > 1 {
                decision.warnings.append(NSLocalizedString("Several patients have this name; none was chosen.", comment: "Patient list import"))
            } else if !byName.isEmpty {
                chosen = byName
                if entry.identifier == nil {
                    decision.warnings.append(NSLocalizedString("Found by name only.", comment: "Patient list import"))
                }
            }
        }
        decision.studies = chosen.map { NSNumber(value: $0) }
        // Included by itself only when the identifier and the name agree.
        decision.include = decision.matchedByIdentifier && !chosen.isEmpty && decision.warnings.isEmpty

        if let first = chosen.first {
            let candidate = candidates[first]
            if entry.age >= 0, let birth = candidate["dateOfBirth"] as? Date {
                let years = Calendar(identifier: .gregorian).dateComponents([.year], from: birth, to: now).year ?? -1
                if years >= 0 && abs(years - entry.age) > 1 {
                    decision.warnings.append(NSLocalizedString("The age differs from the stored birth date.", comment: "Patient list import"))
                }
            } else if entry.age >= 0 {
                decision.warnings.append(NSLocalizedString("No birth date is stored to check the age.", comment: "Patient list import"))
            }
            if let sex = entry.sex, let stored = (candidate["sex"] as? String)?.uppercased().first.map(String.init),
               stored == "M" || stored == "F", stored != sex {
                decision.warnings.append(NSLocalizedString("The sex differs from the stored one.", comment: "Patient list import"))
            }
        }
        return decision
    }
}

@objc(HorosPatientListDecision)
public final class PatientListDecision: NSObject {
    /// Indexes into the candidates the decision was made on.
    @objc public var studies: [NSNumber] = []
    @objc public var matchedByIdentifier = false
    /// Whether the entry is included without the user asking for it.
    @objc public var include = false
    @objc public var warnings: [String] = []
}
