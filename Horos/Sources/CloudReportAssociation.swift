//  Copyright (c) 2026 Horos Project. All rights reserved.
//
//  This file is part of the Horos Project.
//
//  Horos is free software: you can redistribute it and/or modify it under the
//  terms of the GNU Lesser General Public License as published by the Free
//  Software Foundation, version 3 of the License.
//
//  Horos is distributed in the hope that it will be useful, but WITHOUT ANY
//  WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
//  A PARTICULAR PURPOSE. See the GNU Lesser General Public License for details.

import Foundation

/// Whether a Cloud (or Encapsulated PDF / SR) report belongs to a study.
///
/// Horos Cloud writes a DICOM object for the report. When that object carries a
/// new Study Instance UID, import used to open a second study. The same patient
/// name is not a reason to join it: two people can share a name. The report
/// belongs to a study when its Study Instance UID matches, or when it references
/// that study or one of its SOP Instances. The original UID stays on the
/// dictionary so the file on disk is not rewritten.
@objc(HorosCloudReportAssociation)
public final class CloudReportAssociation: NSObject {

    @objc public static let encapsulatedPDFSOPClassUID = "1.2.840.10008.5.1.4.1.1.104.1"
    @objc public static let encapsulatedCDASOPClassUID = "1.2.840.10008.5.1.4.1.1.104.2"
    @objc public static let basicTextSRSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.11"
    @objc public static let enhancedSRSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.22"
    @objc public static let comprehensiveSRSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.33"

    @objc public static let originalStudyUIDKey = "cloudReportOriginalStudyUID"
    @objc public static let decisionKindKey = "kind"
    @objc public static let belongsKey = "belongs"
    @objc public static let rewriteKey = "rewriteStudyID"
    @objc public static let reasonKey = "reason"
    @objc public static let targetStudyUIDKey = "targetStudyUID"
    @objc public static let originalStudyUIDResultKey = "originalStudyUID"
    @objc public static let targetPatientUIDKey = "targetPatientUID"

    @objc public static let kindSameStudy = "same-study"
    @objc public static let kindReferencedStudy = "referenced-study"
    @objc public static let kindReferencedInstance = "referenced-instance"
    @objc public static let kindNameOnly = "name-only"
    @objc public static let kindUnrelated = "unrelated"
    @objc public static let kindNotAReport = "not-a-report"

    private static let osiriXInternalSeries: Set<String> = [
        "OsiriX Annotations SR",
        "OsiriX ROI SR",
        "OsiriX Report SR",
        "OsiriX WindowsState SR",
    ]

    private static let reportSOPClasses: Set<String> = [
        encapsulatedPDFSOPClassUID,
        encapsulatedCDASOPClassUID,
        basicTextSRSOPClassUID,
        enhancedSRSOPClassUID,
        comprehensiveSRSOPClassUID,
        "1.2.840.10008.5.1.4.1.1.88.34", // Comprehensive 3D SR
        "1.2.840.10008.5.1.4.1.1.88.67", // Extensible SR
    ]

    @objc(isReportSOPClass:)
    public static func isReportSOPClass(_ uid: String?) -> Bool {
        guard let uid, !uid.isEmpty else { return false }
        return reportSOPClasses.contains(uid)
    }

    @objc(isCloudManufacturer:)
    public static func isCloudManufacturer(_ name: String?) -> Bool {
        guard let name, !name.isEmpty else { return false }
        let folded = name.lowercased().replacingOccurrences(of: " ", with: "")
        return folded.contains("horoscloud")
    }

    @objc(isReportCandidate:)
    public static func isReportCandidate(_ item: [String: Any]) -> Bool {
        let description = string(item["seriesDescription"])
        if osiriXInternalSeries.contains(description) {
            return false
        }
        if isReportSOPClass(string(item["SOPClassUID"])) {
            return true
        }
        if string(item["modality"]).caseInsensitiveCompare("DOC") == .orderedSame {
            return true
        }
        if isCloudManufacturer(string(item["manufacturer"])) {
            return true
        }
        if description.lowercased().contains("horos cloud") {
            return true
        }
        return false
    }

    @objc(provenanceLineWithOriginalStudyUID:)
    public static func provenanceLine(originalStudyUID: String) -> String {
        "Horos Cloud report originally StudyInstanceUID \(originalStudyUID)"
    }

    /// Whether the report belongs to a known study, and whether grouping should
    /// take that study's UID. Name alone never rewrites the grouping key.
    @objc(decisionForReport:knownStudies:)
    public static func decision(forReport report: [String: Any],
                                knownStudies: [[String: Any]]) -> [String: Any] {
        let reportUID = string(report["studyID"])
        if !isReportCandidate(report) {
            return [
                belongsKey: false,
                rewriteKey: false,
                decisionKindKey: kindNotAReport,
                reasonKey: "not a report DICOM object",
                originalStudyUIDResultKey: reportUID,
            ]
        }

        let catalog = knownStudies.compactMap(StudyIdentity.init(dictionary:))
        let refs = Identity.collect(from: report)

        if let match = catalog.first(where: { $0.studyUID == reportUID && !reportUID.isEmpty }) {
            return [
                belongsKey: true,
                rewriteKey: false,
                decisionKindKey: kindSameStudy,
                reasonKey: "StudyInstanceUID matches the target study",
                targetStudyUIDKey: match.studyUID,
                targetPatientUIDKey: match.patientUID,
                originalStudyUIDResultKey: reportUID,
            ]
        }

        if let match = catalog.first(where: { refs.referencedStudyUIDs.contains($0.studyUID) }) {
            return [
                belongsKey: true,
                rewriteKey: true,
                decisionKindKey: kindReferencedStudy,
                reasonKey: "Referenced Study Instance UID belongs to the target study",
                targetStudyUIDKey: match.studyUID,
                targetPatientUIDKey: match.patientUID,
                originalStudyUIDResultKey: reportUID,
            ]
        }

        if let match = catalog.first(where: { !$0.sopUIDs.isDisjoint(with: refs.referencedSOPUIDs) }) {
            return [
                belongsKey: true,
                rewriteKey: true,
                decisionKindKey: kindReferencedInstance,
                reasonKey: "Referenced SOP Instance UID belongs to the target study",
                targetStudyUIDKey: match.studyUID,
                targetPatientUIDKey: match.patientUID,
                originalStudyUIDResultKey: reportUID,
            ]
        }

        let reportName = string(report["patientName"])
        let nameMatch = catalog.contains {
            !$0.patientName.isEmpty
                && $0.patientName.compare(reportName, options: [.caseInsensitive, .diacriticInsensitive])
                == .orderedSame
        }
        if nameMatch && !reportName.isEmpty {
            return [
                belongsKey: false,
                rewriteKey: false,
                decisionKindKey: kindNameOnly,
                reasonKey: "same patient name is not enough to join a study",
                originalStudyUIDResultKey: reportUID,
            ]
        }

        return [
            belongsKey: false,
            rewriteKey: false,
            decisionKindKey: kindUnrelated,
            reasonKey: "StudyInstanceUID and references do not belong to a known study",
            originalStudyUIDResultKey: reportUID,
        ]
    }

    /// Rewrites the grouping key on report dictionaries that belong by reference.
    /// Dictionaries that are not mutable are left alone. The DICOM file is not
    /// rewritten: the original Study Instance UID remains the provenance.
    @objc(associateReportsInFiles:existingStudies:)
    public static func associateReports(inFiles files: NSArray, existingStudies: [Any]) {
        let dicts = files.compactMap { $0 as? NSMutableDictionary }
        for dict in dicts {
            mergeFileIdentity(into: dict)
        }

        var catalog: [[String: Any]] = existingStudies.compactMap(asStringKeyedDictionary)
        for dict in dicts where !isReportCandidate(dictionary(dict)) {
            catalog.append(dictionary(dict))
        }

        for dict in dicts where isReportCandidate(dictionary(dict)) {
            let decided = decision(forReport: dictionary(dict), knownStudies: catalog)
            let rewrite = (decided[rewriteKey] as? Bool)
                ?? ((decided[rewriteKey] as? NSNumber)?.boolValue ?? false)
            guard rewrite,
                  let target = decided[targetStudyUIDKey] as? String,
                  !target.isEmpty
            else { continue }
            let original = string(dict[originalStudyUIDKey])
            let current = string(dict["studyID"])
            let kept = original.isEmpty ? current : original
            dict[originalStudyUIDKey] = kept
            dict["studyID"] = target
            if let patientUID = decided[targetPatientUIDKey] as? String, !patientUID.isEmpty {
                dict["patientUID"] = patientUID
            }
            if dict["comment"] == nil {
                dict["comment"] = provenanceLine(originalStudyUID: kept)
            }
            NSLog("HorosCloudReportAssociation: grouping %@ under %@ (%@)",
                  kept, target, string(decided[reasonKey]))
        }
    }

    /// Study Instance UID, references and identity tags from a Part 10 file.
    @objc(identityFromFileAtPath:)
    public static func identity(fromFileAtPath path: String) -> [String: Any]? {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)) else { return nil }
        return DICOMUIDReader.identity(from: data)
    }

    private static func mergeFileIdentity(into dict: NSMutableDictionary) {
        let path = string(dict["filePath"])
        guard !path.isEmpty, let identity = identity(fromFileAtPath: path) else { return }
        if string(dict["studyID"]).isEmpty, let study = identity["studyID"] {
            dict["studyID"] = study
        }
        if dict["SOPClassUID"] == nil, let sop = identity["SOPClassUID"] {
            dict["SOPClassUID"] = sop
        }
        if dict["SOPUID"] == nil, let sop = identity["SOPUID"] {
            dict["SOPUID"] = sop
        }
        if dict["manufacturer"] == nil, let manufacturer = identity["manufacturer"] {
            dict["manufacturer"] = manufacturer
        }
        if dict["modality"] == nil, let modality = identity["modality"] {
            dict["modality"] = modality
        }
        if dict["seriesDescription"] == nil, let description = identity["seriesDescription"] {
            dict["seriesDescription"] = description
        }
        if dict["patientName"] == nil, let name = identity["patientName"] {
            dict["patientName"] = name
        }
        if dict["patientID"] == nil, let patientID = identity["patientID"] {
            dict["patientID"] = patientID
        }
        dict["referencedSOPInstanceUIDs"] = union(
            dict["referencedSOPInstanceUIDs"], identity["referencedSOPInstanceUIDs"])
        dict["referencedStudyUIDs"] = union(
            dict["referencedStudyUIDs"], identity["referencedStudyUIDs"])
    }

    private static func dictionary(_ dict: NSMutableDictionary) -> [String: Any] {
        asStringKeyedDictionary(dict) ?? [:]
    }

    private static func asStringKeyedDictionary(_ item: Any) -> [String: Any]? {
        if let typed = item as? [String: Any] {
            return typed
        }
        guard let ns = item as? NSDictionary else { return nil }
        var mapped: [String: Any] = [:]
        ns.enumerateKeysAndObjects { key, value, _ in
            if let key = key as? String {
                mapped[key] = value
            }
        }
        return mapped
    }

    fileprivate static func string(_ value: Any?) -> String {
        if let text = value as? String { return text }
        if let number = value as? NSNumber { return number.stringValue }
        return ""
    }

    fileprivate static func strings(_ value: Any?) -> [String] {
        if let text = value as? String, !text.isEmpty { return [text] }
        if let array = value as? [String] { return array.filter { !$0.isEmpty } }
        if let array = value as? [Any] {
            return array.map { string($0) }.filter { !$0.isEmpty }
        }
        return []
    }

    private static func union(_ first: Any?, _ second: Any?) -> [String] {
        Array(Set(strings(first) + strings(second))).sorted()
    }
}

private struct StudyIdentity {
    let studyUID: String
    let patientUID: String
    let patientName: String
    let patientID: String
    let sopUIDs: Set<String>

    init?(dictionary: [String: Any]) {
        let studyUID = CloudReportAssociation.string(dictionary["studyID"])
        if studyUID.isEmpty { return nil }
        self.studyUID = studyUID
        patientUID = CloudReportAssociation.string(dictionary["patientUID"])
        patientName = CloudReportAssociation.string(dictionary["patientName"])
        patientID = CloudReportAssociation.string(dictionary["patientID"])
        sopUIDs = Set(CloudReportAssociation.strings(dictionary["SOPUIDs"])
            + CloudReportAssociation.strings(dictionary["SOPUID"]))
    }
}

private struct Identity {
    var referencedStudyUIDs: Set<String> = []
    var referencedSOPUIDs: Set<String> = []

    static func collect(from dictionary: [String: Any]) -> Identity {
        var identity = Identity()
        identity.referencedStudyUIDs.formUnion(CloudReportAssociation.strings(dictionary["referencedStudyUIDs"]))
        identity.referencedSOPUIDs.formUnion(CloudReportAssociation.strings(dictionary["referencedSOPInstanceUIDs"]))
        identity.referencedSOPUIDs.formUnion(CloudReportAssociation.strings(dictionary["referencedSOPInstanceUID"]))
        return identity
    }
}

/// Enough of a Part 10 reader to recover Study Instance UID and references.
/// Explicit VR little endian is the transfer syntax of the synthetic fixtures;
/// implicit VR little endian is accepted for the dataset after the meta header.
private enum DICOMUIDReader {
    static func identity(from data: Data) -> [String: Any]? {
        guard data.count > 132,
              data[128..<132] == Data("DICM".utf8)
        else { return nil }
        var reader = Reader(data: data, offset: 132, explicit: true, littleEndian: true)
        var transferSyntax = "1.2.840.10008.1.2.1"
        var tags = CollectedTags()
        reader.readDataset(into: &tags, inSequence: 0, stopGroup: 0x0003) { tag, vr, bytes in
            if tag == 0x0002_0010 {
                transferSyntax = decodeUI(bytes)
            }
        }
        reader.explicit = transferSyntax != "1.2.840.10008.1.2"
        reader.littleEndian = transferSyntax != "1.2.840.10008.1.2.2"
        reader.readDataset(into: &tags, inSequence: 0, stopGroup: nil, onElement: nil)
        guard !tags.studyUID.isEmpty || !tags.sopClassUID.isEmpty else { return nil }
        var result: [String: Any] = [:]
        if !tags.studyUID.isEmpty { result["studyID"] = tags.studyUID }
        if !tags.sopClassUID.isEmpty { result["SOPClassUID"] = tags.sopClassUID }
        if !tags.sopInstanceUID.isEmpty { result["SOPUID"] = tags.sopInstanceUID }
        if !tags.patientName.isEmpty { result["patientName"] = tags.patientName }
        if !tags.patientID.isEmpty { result["patientID"] = tags.patientID }
        if !tags.modality.isEmpty { result["modality"] = tags.modality }
        if !tags.manufacturer.isEmpty { result["manufacturer"] = tags.manufacturer }
        if !tags.seriesDescription.isEmpty { result["seriesDescription"] = tags.seriesDescription }
        if !tags.referencedStudyUIDs.isEmpty {
            result["referencedStudyUIDs"] = Array(tags.referencedStudyUIDs).sorted()
        }
        if !tags.referencedSOPUIDs.isEmpty {
            result["referencedSOPInstanceUIDs"] = Array(tags.referencedSOPUIDs).sorted()
        }
        return result
    }

    private static func decodeUI(_ bytes: Data) -> String {
        String(data: bytes, encoding: .ascii)?
            .trimmingCharacters(in: CharacterSet(charactersIn: "\0 "))
            ?? ""
    }
}

private struct CollectedTags {
    var studyUID = ""
    var sopClassUID = ""
    var sopInstanceUID = ""
    var patientName = ""
    var patientID = ""
    var modality = ""
    var manufacturer = ""
    var seriesDescription = ""
    var referencedStudyUIDs = Set<String>()
    var referencedSOPUIDs = Set<String>()
}

private struct Reader {
    let data: Data
    var offset: Int
    var explicit: Bool
    var littleEndian: Bool

    private let itemStart: UInt32 = 0xFFFE_E000
    private let itemDelim: UInt32 = 0xFFFE_E00D
    private let seqDelim: UInt32 = 0xFFFE_E0DD
    private let longExplicit: Set<String> = [
        "OB", "OD", "OF", "OL", "OV", "OW", "SQ", "SV", "UC", "UN", "UR", "UT", "UV",
    ]

    mutating func readDataset(into tags: inout CollectedTags,
                               inSequence: UInt32,
                               stopGroup: UInt16?,
                               onElement: ((UInt32, String, Data) -> Void)?) {
        while offset + 8 <= data.count {
            let tag = peekTag()
            if let stopGroup, UInt16(tag >> 16) >= stopGroup {
                return
            }
            if tag == itemDelim || tag == seqDelim {
                _ = readTag()
                _ = readUInt32()
                if tag == seqDelim || inSequence != 0 {
                    return
                }
                continue
            }
            if tag == itemStart {
                _ = readTag()
                let length = readUInt32()
                if length == 0xFFFF_FFFF {
                    readDataset(into: &tags, inSequence: inSequence, stopGroup: stopGroup, onElement: onElement)
                } else {
                    let end = min(data.count, offset + Int(length))
                    var nested = Reader(data: data, offset: offset, explicit: explicit, littleEndian: littleEndian)
                    nested.readDataset(into: &tags, inSequence: inSequence, stopGroup: stopGroup, onElement: onElement)
                    offset = end
                }
                continue
            }

            _ = readTag()
            let vr: String
            let length: Int
            if explicit && !isDelimitation(tag) {
                vr = readVR()
                if longExplicit.contains(vr) {
                    offset += 2
                    length = Int(readUInt32())
                } else {
                    length = Int(readUInt16())
                }
            } else {
                vr = ""
                length = Int(readUInt32())
            }

            if length == 0xFFFF_FFFF || vr == "SQ" || tag == 0x0008_1110 || tag == 0x0008_1115
                || tag == 0x0008_1140 || tag == 0x0040_A375 || tag == 0x0008_1199 {
                if length == 0xFFFF_FFFF {
                    readDataset(into: &tags, inSequence: tag, stopGroup: stopGroup, onElement: onElement)
                } else if vr == "SQ" || isSequenceTag(tag) {
                    let end = min(data.count, offset + length)
                    var nested = Reader(data: data, offset: offset, explicit: explicit, littleEndian: littleEndian)
                    nested.readDataset(into: &tags, inSequence: tag, stopGroup: stopGroup, onElement: onElement)
                    offset = end
                } else {
                    consume(length)
                }
                continue
            }

            if tag == 0x7FE0_0010 || tag == 0x0042_0011 {
                consume(length)
                continue
            }

            let bytes = consume(length)
            onElement?(tag, vr, bytes)
            record(tag, inSequence: inSequence, bytes: bytes, into: &tags)
        }
    }

    private func isSequenceTag(_ tag: UInt32) -> Bool {
        tag == 0x0008_1110 || tag == 0x0008_1115 || tag == 0x0008_1140
            || tag == 0x0008_1199 || tag == 0x0040_A375 || tag == 0x0008_2112
    }

    private func isDelimitation(_ tag: UInt32) -> Bool {
        tag == itemStart || tag == itemDelim || tag == seqDelim
    }

    private mutating func record(_ tag: UInt32, inSequence: UInt32, bytes: Data,
                                  into tags: inout CollectedTags) {
        let text = String(data: bytes, encoding: .ascii)?
            .trimmingCharacters(in: CharacterSet(charactersIn: "\0 "))
            ?? ""
        guard !text.isEmpty else { return }
        switch tag {
        case 0x0020_000D:
            if inSequence == 0 && tags.studyUID.isEmpty {
                tags.studyUID = text
            } else if inSequence != 0 {
                tags.referencedStudyUIDs.insert(text)
            }
        case 0x0008_0016:
            if inSequence == 0 { tags.sopClassUID = text }
        case 0x0008_0018:
            if inSequence == 0 { tags.sopInstanceUID = text }
        case 0x0010_0010:
            if inSequence == 0 { tags.patientName = text }
        case 0x0010_0020:
            if inSequence == 0 { tags.patientID = text }
        case 0x0008_0060:
            if inSequence == 0 { tags.modality = text }
        case 0x0008_0070:
            if inSequence == 0 { tags.manufacturer = text }
        case 0x0008_103E:
            if inSequence == 0 { tags.seriesDescription = text }
        case 0x0008_1155:
            if inSequence == 0x0008_1110 {
                tags.referencedStudyUIDs.insert(text)
            } else {
                tags.referencedSOPUIDs.insert(text)
            }
        default:
            break
        }
    }

    private func peekTag() -> UInt32 {
        guard offset + 4 <= data.count else { return 0 }
        let group = readUInt16(at: offset)
        let element = readUInt16(at: offset + 2)
        return (UInt32(group) << 16) | UInt32(element)
    }

    private mutating func readTag() -> UInt32 {
        let tag = peekTag()
        offset += 4
        return tag
    }

    private mutating func readVR() -> String {
        guard offset + 2 <= data.count else { return "" }
        let vr = String(data: data[offset..<offset + 2], encoding: .ascii) ?? ""
        offset += 2
        return vr
    }

    private mutating func readUInt16() -> UInt16 {
        let value = readUInt16(at: offset)
        offset += 2
        return value
    }

    private mutating func readUInt32() -> UInt32 {
        let value = readUInt32(at: offset)
        offset += 4
        return value
    }

    private func readUInt16(at position: Int) -> UInt16 {
        guard position + 2 <= data.count else { return 0 }
        let lo = UInt16(data[position])
        let hi = UInt16(data[position + 1])
        return littleEndian ? lo | (hi << 8) : (lo << 8) | hi
    }

    private func readUInt32(at position: Int) -> UInt32 {
        guard position + 4 <= data.count else { return 0 }
        let b0 = UInt32(data[position])
        let b1 = UInt32(data[position + 1])
        let b2 = UInt32(data[position + 2])
        let b3 = UInt32(data[position + 3])
        if littleEndian {
            return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
        }
        return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
    }

    private mutating func consume(_ length: Int) -> Data {
        guard length >= 0 else { return Data() }
        let end = min(data.count, offset + length)
        let slice = data.subdata(in: offset..<end)
        offset = end
        return slice
    }
}
