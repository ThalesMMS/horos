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

import CryptoKit
import Foundation

/// CSV / Basic Text SR surgical-log import.
///
/// Procedures are stored as DICOM Basic Text SR objects, not a sidecar table.
/// Preview never writes. Identity uses patient ID (including a historical ID
/// still carried in `patientUID`); name similarity is not a merge key.
/// Third-party SR objects stay ordinary structured reports.
@objc(HorosSurgicalProcedureImport)
public final class SurgicalProcedureImport: NSObject {

    @objc public static let basicTextSRSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.11"
    @objc public static let comprehensiveSRSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.33"
    @objc public static let surgicalSeriesDescription = "Horos Surgical Procedure SR"
    /// `errAEEventNotPermitted` — same Automation denial Mail and other hosts report.
    @objc public static let appleEventsDeniedErrorNumber = -1743
    /// `errAEEventWouldRequireUserConsent`
    @objc public static let appleEventsConsentRequiredErrorNumber = -1744
    /// `kLSApplicationNotFoundErr` when Numbers is not installed.
    @objc public static let numbersMissingErrorNumber = -10814
    @objc public static let requiredColumns = [
        "Date", "Name", "ID", "Operation", "Diagnosis", "Results", "Optics", "Assistants",
    ]

    @objc public static func date(from text: String) -> Date? { parseDate(text) }

    public static func parseCSV(_ text: String, sourcePath: String = "") throws -> SurgicalProcedureTable {
        var body = text
        if body.hasPrefix("\u{FEFF}") { body.removeFirst() }
        let records = try csvRecords(body)
        guard let header = records.first, header.isEmpty == false else {
            throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
        }
        var columns: [String: Int] = [:]
        for (index, name) in header.enumerated() {
            let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
            let key = requiredColumns.first { $0.caseInsensitiveCompare(trimmed) == .orderedSame }
            guard let key else { continue }
            if columns[key] != nil {
                throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
            }
            columns[key] = index
        }
        let missing = requiredColumns.filter { columns[$0] == nil }
        if missing.isEmpty == false { throw SurgicalProcedureImportError.missingColumns(missing) }
        var rows: [SurgicalProcedureLogRow] = []
        for (offset, record) in records.dropFirst().enumerated() {
            func value(_ name: String) -> String {
                guard let index = columns[name], index < record.count else { return "" }
                return clean(record[index])
            }
            if requiredColumns.map(value).allSatisfy(\.isEmpty) { continue }
            rows.append(SurgicalProcedureLogRow(
                sourceRow: offset + 2, sourcePath: sourcePath, procedureDate: parseDate(value("Date")),
                dateText: value("Date"), name: value("Name"), patientID: value("ID"),
                operation: value("Operation"), diagnosis: value("Diagnosis"), results: value("Results"),
                optics: value("Optics"), assistants: value("Assistants")))
        }
        return SurgicalProcedureTable(sourcePath: sourcePath, rows: rows)
    }

    public static func diagnoseSource(at url: URL, numbersAvailable: Bool, appleEventsAuthorized: Bool) -> SurgicalProcedureSourceDiagnosis {
        diagnoseSource(at: url, numbersAvailable: numbersAvailable,
                       automationStatus: appleEventsAuthorized ? 0 : appleEventsDeniedErrorNumber)
    }

    public static func diagnoseSource(at url: URL, numbersAvailable: Bool, automationStatus: Int) -> SurgicalProcedureSourceDiagnosis {
        let ext = url.pathExtension.lowercased()
        if ext == "numbers" {
            if numbersAvailable == false {
                return SurgicalProcedureSourceDiagnosis(
                    kind: .numbersMissing,
                    message: String(format: NSLocalizedString("Numbers is not installed (error %ld). Export the surgical log as CSV and import that file.", comment: ""), Int(numbersMissingErrorNumber)),
                    errorNumber: numbersMissingErrorNumber)
            }
            if automationStatus != 0 {
                return SurgicalProcedureSourceDiagnosis(
                    kind: .appleEventsDenied,
                    message: String(format: NSLocalizedString("Horos is not allowed to control Numbers (error %ld). Export the log as CSV, or grant Automation access in System Settings > Privacy & Security > Automation and try again.", comment: ""), automationStatus),
                    errorNumber: automationStatus)
            }
            return SurgicalProcedureSourceDiagnosis(
                kind: .numbersReady,
                message: NSLocalizedString("Numbers is available. Export the surgical log as CSV to import it in this Horos build.", comment: ""),
                errorNumber: 0)
        }
        if ext == "csv" || ext == "txt" || ext.isEmpty {
            return SurgicalProcedureSourceDiagnosis(kind: .csv, message: "", errorNumber: 0)
        }
        return SurgicalProcedureSourceDiagnosis(
            kind: .invalidFile,
            message: NSLocalizedString("The surgical log could not be read.", comment: ""),
            errorNumber: 0)
    }

    public static func preview(table: SurgicalProcedureTable, patients: [SurgicalProcedurePatient], existing: [SurgicalProcedureRecord]) -> SurgicalProcedurePreview {
        let matcher = PatientMatcher(patients: patients)
        var eventOccurrences: [String: Int] = [:]
        var rows: [SurgicalProcedurePreviewRow] = []
        let existingByEvent = Dictionary(uniqueKeysWithValues: existing.map { ($0.eventID, $0) })
        for row in table.rows {
            if row.procedureDate == nil {
                rows.append(SurgicalProcedurePreviewRow(row: row.sourceRow, action: .skipped, patient: row.name, details: NSLocalizedString("Missing or invalid surgery date.", comment: ""), record: nil))
                continue
            }
            if row.operation.isEmpty || row.name.isEmpty {
                rows.append(SurgicalProcedurePreviewRow(row: row.sourceRow, action: .skipped, patient: row.name, details: NSLocalizedString("Missing Name or Operation.", comment: ""), record: nil))
                continue
            }
            switch matcher.match(name: row.name, patientID: row.patientID) {
            case .none(let reason):
                rows.append(SurgicalProcedurePreviewRow(row: row.sourceRow, action: .skipped, patient: row.name, details: reason, record: nil))
            case .review(let details):
                rows.append(SurgicalProcedurePreviewRow(row: row.sourceRow, action: .review, patient: row.name, details: details, record: nil, pendingRow: row))
            case .matched(let patient):
                let prepared = prepare(row: row, patient: patient, occurrences: &eventOccurrences)
                if let current = existingByEvent[prepared.eventID] {
                    let action: SurgicalProcedurePreviewAction = materialFields(prepared) == materialFields(current) ? .unchanged : .update
                    var record = prepared
                    record.sopInstanceUID = current.sopInstanceUID
                    record.seriesInstanceUID = current.seriesInstanceUID
                    record.studyInstanceUID = current.studyInstanceUID
                    record.importedAt = current.importedAt
                    rows.append(SurgicalProcedurePreviewRow(row: row.sourceRow, action: action, patient: patient.name, details: action == .update ? "Update" : "Unchanged", record: record))
                } else {
                    rows.append(SurgicalProcedurePreviewRow(row: row.sourceRow, action: .add, patient: patient.name, details: "Add", record: prepared))
                }
            }
        }
        return SurgicalProcedurePreview(rows: rows, patients: patients, existing: existing, table: table)
    }

    public static func commit(_ preview: SurgicalProcedurePreview, into store: inout [SurgicalProcedureRecord], now: Date) throws -> SurgicalProcedureCommitResult {
        guard store.count == preview.existing.count else {
            throw SurgicalProcedureImportError.writeFailed(NSLocalizedString("The surgical procedure records could not be written: the database changed after this preview was created.", comment: ""))
        }
        var inserted = 0
        var updated = 0
        var byEvent = Dictionary(uniqueKeysWithValues: store.map { ($0.eventID, $0) })
        for row in preview.changes {
            guard var record = row.record else { continue }
            switch row.action {
            case .add:
                if byEvent[record.eventID] != nil {
                    throw SurgicalProcedureImportError.writeFailed(NSLocalizedString("The surgical procedure records could not be written: the database changed after this preview was created.", comment: ""))
                }
                record.importedAt = now
                record.updatedAt = now
                assignUIDs(&record)
                byEvent[record.eventID] = record
                inserted += 1
            case .update:
                guard let current = byEvent[record.eventID] else {
                    throw SurgicalProcedureImportError.writeFailed(NSLocalizedString("The surgical procedure records could not be written: the database changed after this preview was created.", comment: ""))
                }
                record.sopInstanceUID = current.sopInstanceUID
                record.seriesInstanceUID = current.seriesInstanceUID
                record.studyInstanceUID = current.studyInstanceUID
                record.importedAt = current.importedAt
                record.updatedAt = now
                byEvent[record.eventID] = record
                updated += 1
            default:
                continue
            }
        }
        store = preview.existing.map { byEvent[$0.eventID] ?? $0 }
        for record in byEvent.values where preview.existing.contains(where: { $0.eventID == record.eventID }) == false {
            store.append(record)
        }
        return SurgicalProcedureCommitResult(inserted: inserted, updated: updated, unchanged: preview.rows.filter { $0.action == .unchanged }.count)
    }

    public static func encodeBasicTextSR(_ record: SurgicalProcedureRecord) throws -> Data {
        var working = record
        assignUIDs(&working)
        return try writeStructuredReport(sopClassUID: basicTextSRSOPClassUID, seriesDescription: surgicalSeriesDescription, record: working, json: try encodeJSON(working), extraText: nil)
    }

    public static func decodeBasicTextSR(_ data: Data) throws -> SurgicalProcedureRecord {
        let parsed = try DicomParser.parse(data)
        guard let json = parsed.recordJSON, let record = decodeJSON(json) else {
            throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
        }
        var decoded = record
        decoded.sopClassUID = parsed.sopClassUID.isEmpty ? basicTextSRSOPClassUID : parsed.sopClassUID
        decoded.modality = parsed.modality.isEmpty ? "SR" : parsed.modality
        decoded.sopInstanceUID = parsed.sopInstanceUID
        decoded.seriesInstanceUID = parsed.seriesInstanceUID
        decoded.studyInstanceUID = parsed.studyInstanceUID
        return decoded
    }

    public static func isSurgicalProcedureSR(_ data: Data) -> Bool {
        guard let parsed = try? DicomParser.parse(data) else { return false }
        return isSurgicalProcedureSR(sopClassUID: parsed.sopClassUID, seriesDescription: parsed.seriesDescription)
    }

    public static func isSurgicalProcedureSR(sopClassUID: String, seriesDescription: String) -> Bool {
        isStructuredReport(sopClassUID: sopClassUID) && seriesDescription == surgicalSeriesDescription
    }

    public static func isStructuredReport(sopClassUID: String) -> Bool {
        [basicTextSRSOPClassUID, "1.2.840.10008.5.1.4.1.1.88.22", comprehensiveSRSOPClassUID,
         "1.2.840.10008.5.1.4.1.1.88.34", "1.2.840.10008.5.1.4.1.1.88.67"].contains(sopClassUID)
    }

    public static func encodeGenericStructuredReport(sopClassUID: String, seriesDescription: String, text: String) throws -> Data {
        let stub = SurgicalProcedureRecord(
            eventID: "foreign", patientKey: "foreign", procedureDate: Date(timeIntervalSince1970: 0),
            sourcePatientName: "", sourcePatientID: "", matchedPatientName: "FOREIGN", matchedPatientID: "FOREIGN",
            matchedPatientUID: "", matchedBirthDate: nil, anchorStudyInstanceUID: "", operation: text,
            diagnosis: "", results: "", optics: "", assistants: "", sourceFile: "", sourceRow: 0,
            sourceFingerprint: "", importedAt: Date(timeIntervalSince1970: 0), updatedAt: Date(timeIntervalSince1970: 0))
        return try writeStructuredReport(sopClassUID: sopClassUID, seriesDescription: seriesDescription, record: stub, json: nil, extraText: text)
    }

    static func prepare(row: SurgicalProcedureLogRow, patient: SurgicalProcedurePatient, occurrences: inout [String: Int]) -> SurgicalProcedureRecord {
        let date = row.procedureDate!
        let stableName = primaryNameKey(patient.name).isEmpty ? primaryNameKey(row.name) : primaryNameKey(patient.name)
        var identity = "\(stableName)|\(patient.birthDate.map(calendarDateString) ?? "")"
        if patient.birthDate == nil { identity += "|\(normalizeID(patient.patientID))" }
        let patientKey = String(sha256(identity).prefix(32))
        let operationKey = normalizedOperation(row.operation)
        let eventIdentity = "\(patientKey)|\(calendarDateString(date))|\(operationKey)"
        let occurrence = occurrences[eventIdentity, default: 0]
        occurrences[eventIdentity] = occurrence + 1
        let eventID = sha256(occurrence == 0 ? eventIdentity : "\(eventIdentity)|occurrence:\(occurrence + 1)")
        let fingerprint = sha256([
            row.name, row.patientID, patient.name, patient.patientID, patient.patientUID,
            patient.birthDate.map(calendarDateString) ?? "", patient.studyInstanceUID,
            row.operation, operationKey, row.diagnosis, row.results, row.optics, row.assistants,
            row.sourcePath, String(row.sourceRow),
        ].joined(separator: "\u{1f}"))
        return SurgicalProcedureRecord(
            eventID: eventID, patientKey: patientKey, procedureDate: date,
            sourcePatientName: row.name, sourcePatientID: row.patientID,
            matchedPatientName: patient.name, matchedPatientID: patient.patientID,
            matchedPatientUID: patient.patientUID, matchedBirthDate: patient.birthDate,
            anchorStudyInstanceUID: patient.studyInstanceUID, operation: row.operation,
            diagnosis: row.diagnosis, results: row.results, optics: row.optics, assistants: row.assistants,
            sourceFile: row.sourcePath, sourceRow: row.sourceRow, sourceFingerprint: fingerprint,
            importedAt: Date.distantPast, updatedAt: Date.distantPast)
    }

    @objc(diagnoseSourceAtPath:numbersAvailable:appleEventsAuthorized:)
    public static func diagnoseSource(atPath path: String, numbersAvailable: Bool, appleEventsAuthorized: Bool) -> [String: String] {
        let diagnosis = diagnoseSource(at: URL(fileURLWithPath: path), numbersAvailable: numbersAvailable, appleEventsAuthorized: appleEventsAuthorized)
        let kind: String
        switch diagnosis.kind {
        case .csv: kind = "csv"
        case .numbersReady: kind = "numbersReady"
        case .numbersMissing: kind = "numbersMissing"
        case .appleEventsDenied: kind = "appleEventsDenied"
        case .invalidFile: kind = "invalidFile"
        }
        return ["kind": kind, "message": diagnosis.message, "errorNumber": String(diagnosis.errorNumber)]
    }

    @objc(diagnoseSourceAtPath:numbersAvailable:automationStatus:)
    public static func diagnoseSource(atPath path: String, numbersAvailable: Bool, automationStatus: Int) -> [String: String] {
        let diagnosis = diagnoseSource(at: URL(fileURLWithPath: path), numbersAvailable: numbersAvailable, automationStatus: automationStatus)
        let kind: String
        switch diagnosis.kind {
        case .csv: kind = "csv"
        case .numbersReady: kind = "numbersReady"
        case .numbersMissing: kind = "numbersMissing"
        case .appleEventsDenied: kind = "appleEventsDenied"
        case .invalidFile: kind = "invalidFile"
        }
        return ["kind": kind, "message": diagnosis.message, "errorNumber": String(diagnosis.errorNumber)]
    }

    public static let numbersReaderScript = SurgicalNumbersReader.script

    public static func timeline(surgical: [SurgicalProcedureRecord], otherSR: [Data] = []) -> [SurgicalProcedureTimelineEvent] {
        for data in otherSR {
            if isSurgicalProcedureSR(data) == false { continue }
        }
        return surgical
            .map { record in
                SurgicalProcedureTimelineEvent(
                    eventID: record.eventID,
                    date: record.procedureDate,
                    operation: record.operation,
                    diagnosis: record.diagnosis,
                    patientName: record.matchedPatientName,
                    patientID: record.matchedPatientID,
                    displayModality: "SURG",
                    dicomModality: record.modality.isEmpty ? "SR" : record.modality
                )
            }
            .sorted {
                if $0.date != $1.date { return $0.date > $1.date }
                return $0.operation.localizedCaseInsensitiveCompare($1.operation) == .orderedAscending
            }
    }

    @objc(timelineEventsFromSRPaths:)
    public static func timelineEvents(fromSRPaths paths: [String]) -> [[String: Any]] {
        let records: [SurgicalProcedureRecord] = paths.compactMap { path in
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
                  isSurgicalProcedureSR(data) else { return nil }
            return try? decodeBasicTextSR(data)
        }
        return timeline(surgical: records).map { event in
            [
                "eventID": event.eventID,
                "operation": event.operation,
                "diagnosis": event.diagnosis,
                "patientName": event.patientName,
                "patientID": event.patientID,
                "displayModality": event.displayModality,
                "dicomModality": event.dicomModality,
                "date": event.date,
            ]
        }
    }

    public static func table(fromNumbersJSON json: String, sourcePath: String) throws -> SurgicalProcedureTable {
        guard let data = json.data(using: .utf8) else {
            throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
        }
        let decoded: NumbersLogJSON
        do {
            decoded = try JSONDecoder().decode(NumbersLogJSON.self, from: data)
        } catch {
            throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
        }
        guard let header = decoded.rows.first, header.isEmpty == false else {
            throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
        }
        var columns: [String: Int] = [:]
        for (index, name) in header.enumerated() {
            let key = requiredColumns.first { $0.caseInsensitiveCompare(clean(name)) == .orderedSame }
            guard let key else { continue }
            if columns[key] != nil {
                throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
            }
            columns[key] = index
        }
        let missing = requiredColumns.filter { columns[$0] == nil }
        if missing.isEmpty == false { throw SurgicalProcedureImportError.missingColumns(missing) }
        var rows: [SurgicalProcedureLogRow] = []
        for (offset, record) in decoded.rows.dropFirst().enumerated() {
            func value(_ name: String) -> String {
                guard let index = columns[name], index < record.count else { return "" }
                return clean(record[index])
            }
            if requiredColumns.map(value).allSatisfy(\.isEmpty) { continue }
            rows.append(SurgicalProcedureLogRow(
                sourceRow: decoded.headerRow + offset + 1, sourcePath: sourcePath, procedureDate: parseDate(value("Date")),
                dateText: value("Date"), name: value("Name"), patientID: value("ID"),
                operation: value("Operation"), diagnosis: value("Diagnosis"), results: value("Results"),
                optics: value("Optics"), assistants: value("Assistants")))
        }
        return SurgicalProcedureTable(sourcePath: sourcePath, rows: rows)
    }

    static func patients(from dictionaries: [[AnyHashable: Any]]) -> [SurgicalProcedurePatient] {
        dictionaries.compactMap { row in
            let name = row["name"] as? String ?? ""
            let patientID = row["patientID"] as? String ?? ""
            guard name.isEmpty == false || patientID.isEmpty == false else { return nil }
            return SurgicalProcedurePatient(
                name: name, patientID: patientID,
                patientUID: row["patientUID"] as? String ?? "",
                birthDate: row["dateOfBirth"] as? Date,
                studyInstanceUID: row["studyInstanceUID"] as? String ?? "")
        }
    }
}

public enum SurgicalProcedureImportError: Error, Equatable, LocalizedError {
    case missingColumns([String])
    case invalidFile(String)
    case writeFailed(String)
    public var errorDescription: String? {
        switch self {
        case .missingColumns(let columns):
            return String(format: NSLocalizedString("The table is missing required columns: %@", comment: ""), columns.joined(separator: ", "))
        case .invalidFile(let message), .writeFailed(let message):
            return message
        }
    }
}

public enum SurgicalProcedurePreviewAction: String, Equatable { case add, update, unchanged, skipped, review }
public enum SurgicalProcedureSourceKind: Equatable { case csv, numbersReady, numbersMissing, appleEventsDenied, invalidFile }
public struct SurgicalProcedureSourceDiagnosis: Equatable {
    public var kind: SurgicalProcedureSourceKind
    public var message: String
    public var errorNumber: Int
    public init(kind: SurgicalProcedureSourceKind, message: String, errorNumber: Int = 0) {
        self.kind = kind
        self.message = message
        self.errorNumber = errorNumber
    }
}

public struct SurgicalProcedurePatient: Equatable {
    public var name: String
    public var patientID: String
    public var patientUID: String
    public var birthDate: Date?
    public var studyInstanceUID: String
    public init(name: String, patientID: String, patientUID: String, birthDate: Date?, studyInstanceUID: String) {
        self.name = name; self.patientID = patientID; self.patientUID = patientUID
        self.birthDate = birthDate; self.studyInstanceUID = studyInstanceUID
    }
}

public struct SurgicalProcedureLogRow: Equatable {
    public var sourceRow: Int
    public var sourcePath: String
    public var procedureDate: Date?
    public var dateText: String
    public var name: String
    public var patientID: String
    public var operation: String
    public var diagnosis: String
    public var results: String
    public var optics: String
    public var assistants: String
}

public struct SurgicalProcedureTable: Equatable { public var sourcePath: String; public var rows: [SurgicalProcedureLogRow] }

public struct SurgicalProcedureRecord: Equatable, Codable {
    public var eventID: String
    public var patientKey: String
    public var procedureDate: Date
    public var sourcePatientName: String
    public var sourcePatientID: String
    public var matchedPatientName: String
    public var matchedPatientID: String
    public var matchedPatientUID: String
    public var matchedBirthDate: Date?
    public var anchorStudyInstanceUID: String
    public var operation: String
    public var diagnosis: String
    public var results: String
    public var optics: String
    public var assistants: String
    public var sourceFile: String
    public var sourceRow: Int
    public var sourceFingerprint: String
    public var importedAt: Date
    public var updatedAt: Date
    public var sopClassUID: String = SurgicalProcedureImport.basicTextSRSOPClassUID
    public var modality: String = "SR"
    public var sopInstanceUID: String = ""
    public var seriesInstanceUID: String = ""
    public var studyInstanceUID: String = ""
}

public struct SurgicalProcedurePreviewRow: Equatable {
    public var row: Int
    public var action: SurgicalProcedurePreviewAction
    public var patient: String
    public var details: String
    public var record: SurgicalProcedureRecord?
    public var pendingRow: SurgicalProcedureLogRow? = nil
}

public struct SurgicalProcedurePreview: Equatable {
    public var rows: [SurgicalProcedurePreviewRow]
    public var patients: [SurgicalProcedurePatient]
    public var existing: [SurgicalProcedureRecord]
    public var table: SurgicalProcedureTable
    public var changes: [SurgicalProcedurePreviewRow] { rows.filter { $0.action == .add || $0.action == .update } }
    public func confirming(row: Int, patientUID: String) -> SurgicalProcedurePreview {
        guard let patient = patients.first(where: { $0.patientUID == patientUID }) else { return self }
        var copy = self
        var occurrences: [String: Int] = [:]
        copy.rows = rows.map { item in
            guard item.row == row, item.action == .review, let pending = item.pendingRow else { return item }
            let prepared = SurgicalProcedureImport.prepare(row: pending, patient: patient, occurrences: &occurrences)
            return SurgicalProcedurePreviewRow(row: item.row, action: .add, patient: patient.name, details: "Add", record: prepared)
        }
        return copy
    }
}

public struct SurgicalProcedureCommitResult: Equatable {
    public var inserted: Int
    public var updated: Int
    public var unchanged: Int
}

public struct SurgicalProcedureTimelineEvent: Equatable {
    public var eventID: String
    public var date: Date
    public var operation: String
    public var diagnosis: String
    public var patientName: String
    public var patientID: String
    public var displayModality: String
    public var dicomModality: String
    public var displayTitle: String { operation.isEmpty ? "Surgery" : "Surgery: \(operation)" }

    public func displayValue(forColumn identifier: String) -> String {
        switch identifier {
        case "name": return displayTitle
        case "patientID": return patientID
        case "modality": return displayModality
        case "studyName", "seriesDescription": return diagnosis
        case "noFiles", "numberOfImages": return "0"
        default: return ""
        }
    }

    public func detailsHTML() -> String {
        let body = [
            ("Operation", operation),
            ("Diagnosis", diagnosis),
        ].compactMap { title, value -> String? in
            guard value.isEmpty == false else { return nil }
            let escaped = value
                .replacingOccurrences(of: "&", with: "&amp;")
                .replacingOccurrences(of: "<", with: "&lt;")
                .replacingOccurrences(of: ">", with: "&gt;")
            return "<section><h2>\(title)</h2><p>\(escaped)</p></section>"
        }.joined()
        return "<!doctype html><html><body><header><h1>Surgical Procedure</h1></header>\(body)</body></html>"
    }
}

@objc(HorosSurgicalProcedureImportSession)
public final class SurgicalProcedureImportSession: NSObject {
    private var preview: SurgicalProcedurePreview?
    @objc public private(set) var summary = ""
    @objc public var changeCount: Int { preview?.changes.count ?? 0 }

    @objc(prepareCSVAtPath:patients:existingPaths:error:)
    public func prepareCSV(atPath path: String, patients: [[AnyHashable: Any]], existingPaths: [String]) throws {
        let text = try String(contentsOf: URL(fileURLWithPath: path), encoding: .utf8)
        let table = try SurgicalProcedureImport.parseCSV(text, sourcePath: path)
        let people = SurgicalProcedureImport.patients(from: patients)
        let existing: [SurgicalProcedureRecord] = existingPaths.compactMap { path in
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
                  SurgicalProcedureImport.isSurgicalProcedureSR(data) else { return nil }
            return try? SurgicalProcedureImport.decodeBasicTextSR(data)
        }
        let preview = SurgicalProcedureImport.preview(table: table, patients: people, existing: existing)
        self.preview = preview
        let added = preview.rows.filter { $0.action == .add }.count
        let updated = preview.rows.filter { $0.action == .update }.count
        let skipped = preview.rows.filter { $0.action == .skipped }.count
        let review = preview.rows.filter { $0.action == .review }.count
        let unchanged = preview.rows.filter { $0.action == .unchanged }.count
        summary = "Add \(added), update \(updated), unchanged \(unchanged), skipped \(skipped), review \(review)."
    }

    @objc(commitToDirectory:error:)
    public func commit(toDirectory directory: String) throws -> [String] {
        guard let preview else {
            throw SurgicalProcedureImportError.writeFailed(NSLocalizedString("The surgical log could not be read.", comment: ""))
        }
        var store = preview.existing
        _ = try SurgicalProcedureImport.commit(preview, into: &store, now: Date())
        try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
        let changed = Set(preview.changes.compactMap(\.record?.eventID))
        var paths: [String] = []
        for record in store where changed.contains(record.eventID) {
            let data = try SurgicalProcedureImport.encodeBasicTextSR(record)
            let file = record.sopInstanceUID.replacingOccurrences(of: ".", with: "-") + ".dcm"
            let path = (directory as NSString).appendingPathComponent(file)
            try data.write(to: URL(fileURLWithPath: path), options: .atomic)
            paths.append(path)
        }
        return paths
    }
}

private struct MaterialFields: Equatable {
    var procedureDate: String
    var operation: String
    var diagnosis: String
    var results: String
    var optics: String
    var assistants: String
}

private func materialFields(_ record: SurgicalProcedureRecord) -> MaterialFields {
    MaterialFields(procedureDate: calendarDateString(record.procedureDate), operation: record.operation,
                   diagnosis: record.diagnosis, results: record.results, optics: record.optics, assistants: record.assistants)
}

private struct PatientMatcher {
    let patients: [SurgicalProcedurePatient]
    func match(name: String, patientID: String) -> Match {
        let id = normalizeID(patientID)
        if id.isEmpty == false {
            let candidates = patients.filter { normalizeID($0.patientID) == id || historicalIDs($0).contains(id) }
            if candidates.isEmpty {
                return .none(NSLocalizedString("No patient identifier matched this row.", comment: ""))
            }
            let compatible = candidates.filter { namesAreCompatible(name, $0.name) }
            return choose(compatible.isEmpty ? candidates : compatible)
        }
        let exact = patients.filter { exactNameKey($0.name) == exactNameKey(name) && exactNameKey(name).isEmpty == false }
        if exact.isEmpty == false { return choose(exact) }
        return .none(NSLocalizedString("No patient identifier matched this row.", comment: ""))
    }
    private func choose(_ candidates: [SurgicalProcedurePatient]) -> Match {
        guard candidates.isEmpty == false else {
            return .none(NSLocalizedString("No patient identifier matched this row.", comment: ""))
        }
        let births = Set(candidates.compactMap(\.birthDate).map(calendarDateString))
        let names = Set(candidates.map { primaryNameKey($0.name) }.filter { $0.isEmpty == false })
        if births.count > 1 || names.count > 1 {
            return .review(NSLocalizedString("The patient match is ambiguous and needs confirmation.", comment: ""))
        }
        return .matched(candidates[0])
    }
}

private enum Match {
    case matched(SurgicalProcedurePatient)
    case none(String)
    case review(String)
}

private func historicalIDs(_ patient: SurgicalProcedurePatient) -> [String] {
    let pieces = patient.patientUID.split(separator: "-").map(String.init)
    guard pieces.count >= 3 else { return [] }
    let id = normalizeID(pieces[1..<(pieces.count - 1)].joined(separator: "-"))
    return id.isEmpty ? [] : [id]
}

private func assignUIDs(_ record: inout SurgicalProcedureRecord) {
    if record.sopInstanceUID.isEmpty { record.sopInstanceUID = dicomUID(for: record.eventID, component: "sop") }
    if record.seriesInstanceUID.isEmpty { record.seriesInstanceUID = dicomUID(for: record.eventID, component: "series") }
    if record.studyInstanceUID.isEmpty { record.studyInstanceUID = dicomUID(for: record.eventID, component: "study") }
}

private func dicomUID(for eventID: String, component: String) -> String {
    let digest = SHA256.hash(data: Data("horos-surgical|\(eventID)|\(component)".utf8))
    return "2.25." + digest.prefix(12).map { String(format: "%03d", $0) }.joined()
}

private func encodeJSON(_ record: SurgicalProcedureRecord) throws -> String {
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .secondsSince1970
    encoder.outputFormatting = [.sortedKeys]
    let data = try encoder.encode(record)
    guard let json = String(data: data, encoding: .utf8) else {
        throw SurgicalProcedureImportError.writeFailed(NSLocalizedString("The surgical procedure records could not be written: the database changed after this preview was created.", comment: ""))
    }
    return json
}

private func decodeJSON(_ json: String) -> SurgicalProcedureRecord? {
    guard let data = json.data(using: .utf8) else { return nil }
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .secondsSince1970
    return try? decoder.decode(SurgicalProcedureRecord.self, from: data)
}

private func writeStructuredReport(sopClassUID: String, seriesDescription: String, record: SurgicalProcedureRecord, json: String?, extraText: String?) throws -> Data {
    var working = record
    assignUIDs(&working)
    let da = calendarDateCompact(working.procedureDate)
    var dataset = DicomBuffer()
    dataset.ui(0x0008, 0x0016, sopClassUID)
    dataset.ui(0x0008, 0x0018, working.sopInstanceUID)
    dataset.da(0x0008, 0x0020, da)
    dataset.da(0x0008, 0x0023, da)
    dataset.tm(0x0008, 0x0030, "120000")
    dataset.tm(0x0008, 0x0033, "120000")
    dataset.cs(0x0008, 0x0060, "SR")
    dataset.lo(0x0008, 0x0070, "Horos")
    dataset.lo(0x0008, 0x1030, "Surgical Procedure")
    dataset.lo(0x0008, 0x103E, seriesDescription)
    dataset.pn(0x0010, 0x0010, working.matchedPatientName)
    dataset.lo(0x0010, 0x0020, working.matchedPatientID)
    if let birth = working.matchedBirthDate { dataset.da(0x0010, 0x0030, calendarDateCompact(birth)) }
    dataset.ui(0x0020, 0x000D, working.studyInstanceUID)
    dataset.ui(0x0020, 0x000E, working.seriesInstanceUID)
    dataset.integerString(0x0020, 0x0011, "1")
    dataset.integerString(0x0020, 0x0013, "1")
    dataset.cs(0x0040, 0xA040, "CONTAINER")
    dataset.sq(0x0040, 0xA043, [codeItem("18748-4", "LN", "Diagnostic Imaging Report")])
    dataset.cs(0x0040, 0xA050, "SEPARATE")
    dataset.cs(0x0040, 0xA491, "COMPLETE")
    dataset.cs(0x0040, 0xA493, "UNVERIFIED")
    var items: [Data] = []
    if let extraText {
        items.append(textItem("FINDINGS", "99HOROS", "Findings", extraText))
    } else {
        items.append(textItem("OPERATION", "99HOROS", "Operation", working.operation))
        items.append(textItem("DIAGNOSIS", "99HOROS", "Diagnosis", working.diagnosis))
        items.append(textItem("RESULTS", "99HOROS", "Results", working.results))
        items.append(textItem("OPTICS", "99HOROS", "Optics", working.optics))
        items.append(textItem("ASSISTANTS", "99HOROS", "Assistants", working.assistants))
        if let json { items.append(textItem("RECORDJSON", "99HOROS", "Horos Surgical Procedure Record", json)) }
    }
    dataset.sq(0x0040, 0xA730, items)
    var meta = DicomBuffer()
    meta.ob(0x0002, 0x0001, Data([0x00, 0x01]))
    meta.ui(0x0002, 0x0002, sopClassUID)
    meta.ui(0x0002, 0x0003, working.sopInstanceUID)
    meta.ui(0x0002, 0x0010, "1.2.840.10008.1.2.1")
    meta.ui(0x0002, 0x0012, "2.25.383000000000")
    meta.sh(0x0002, 0x0013, "HOROS383")
    var file = Data(count: 128)
    file.append(contentsOf: [0x44, 0x49, 0x43, 0x4D])
    file.append(meta.bytes)
    file.append(dataset.bytes)
    return file
}

private func textItem(_ value: String, _ scheme: String, _ meaning: String, _ text: String) -> Data {
    var item = DicomBuffer()
    item.cs(0x0040, 0xA040, "TEXT")
    item.sq(0x0040, 0xA043, [codeItem(value, scheme, meaning)])
    item.ut(0x0040, 0xA160, text)
    return item.bytes
}

private func codeItem(_ value: String, _ scheme: String, _ meaning: String) -> Data {
    var item = DicomBuffer()
    item.sh(0x0008, 0x0100, value)
    item.sh(0x0008, 0x0102, scheme)
    item.lo(0x0008, 0x0104, meaning)
    return item.bytes
}

private struct DicomBuffer {
    var bytes = Data()
    private let longVR: Set<String> = ["OB", "OD", "OF", "OL", "OW", "SQ", "UC", "UN", "UR", "UT"]
    mutating func cs(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "CS", data: Data(value.utf8), pad: 0x20) }
    mutating func sh(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "SH", string: value, pad: 0x20) }
    mutating func lo(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "LO", string: value, pad: 0x20) }
    mutating func pn(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "PN", string: value, pad: 0x20) }
    mutating func da(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "DA", string: value, pad: 0x20) }
    mutating func tm(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "TM", string: value, pad: 0x20) }
    mutating func integerString(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "IS", string: value, pad: 0x20) }
    mutating func ui(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "UI", string: value, pad: 0x00) }
    mutating func ut(_ g: UInt16, _ e: UInt16, _ value: String) { put(g, e, vr: "UT", data: Data(value.utf8), pad: 0x20) }
    mutating func ob(_ g: UInt16, _ e: UInt16, _ value: Data) { put(g, e, vr: "OB", data: value, pad: 0x00) }
    mutating func sq(_ g: UInt16, _ e: UInt16, _ items: [Data]) {
        var payload = Data()
        for item in items {
            payload.append(contentsOf: tagBytes(0xFFFE, 0xE000))
            var length = UInt32(item.count).littleEndian
            payload.append(Data(bytes: &length, count: 4))
            payload.append(item)
        }
        put(g, e, vr: "SQ", data: payload, pad: 0x00)
    }
    private mutating func put(_ g: UInt16, _ e: UInt16, vr: String, string: String, pad: UInt8) {
        put(g, e, vr: vr, data: Data(string.utf8), pad: pad)
    }
    private mutating func put(_ g: UInt16, _ e: UInt16, vr: String, data: Data, pad: UInt8) {
        bytes.append(contentsOf: tagBytes(g, e))
        bytes.append(contentsOf: vr.utf8)
        var value = data
        if value.count % 2 == 1 { value.append(pad) }
        if longVR.contains(vr) {
            bytes.append(contentsOf: [0, 0])
            var length = UInt32(value.count).littleEndian
            bytes.append(Data(bytes: &length, count: 4))
        } else {
            var length = UInt16(value.count).littleEndian
            bytes.append(Data(bytes: &length, count: 2))
        }
        bytes.append(value)
    }
}

private func tagBytes(_ g: UInt16, _ e: UInt16) -> Data {
    var group = g.littleEndian
    var element = e.littleEndian
    var data = Data()
    data.append(Data(bytes: &group, count: 2))
    data.append(Data(bytes: &element, count: 2))
    return data
}

private struct DicomParsed {
    var sopClassUID = ""
    var sopInstanceUID = ""
    var seriesInstanceUID = ""
    var studyInstanceUID = ""
    var seriesDescription = ""
    var modality = ""
    var recordJSON: String?
}

private enum DicomParser {
    static func parse(_ data: Data) throws -> DicomParsed {
        guard data.count >= 132, data[128..<132].elementsEqual([0x44, 0x49, 0x43, 0x4D]) else {
            throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
        }
        return try parseDataset(data, 132, data.count)
    }

    static func parseDataset(_ data: Data, _ start: Int, _ end: Int) throws -> DicomParsed {
        var parsed = DicomParsed()
        var offset = start
        let long = ["OB", "OD", "OF", "OL", "OW", "SQ", "UC", "UN", "UR", "UT"]
        while offset + 8 <= end {
            let group = u16(data, offset)
            let element = u16(data, offset + 2)
            offset += 4
            if group == 0xFFFE {
                let length = Int(u32(data, offset))
                offset += 4
                if element == 0xE000, length != 0xFFFFFFFF, offset + length <= end {
                    let nested = try parseDataset(data, offset, offset + length)
                    if parsed.recordJSON == nil { parsed.recordJSON = nested.recordJSON }
                    offset += length
                }
                continue
            }
            let vr = String(data: data[offset..<offset + 2], encoding: .ascii) ?? ""
            offset += 2
            let length: Int
            if long.contains(vr) {
                offset += 2
                length = Int(u32(data, offset))
                offset += 4
            } else {
                length = Int(u16(data, offset))
                offset += 2
            }
            guard offset + length <= end else { break }
            let value = data.subdata(in: offset..<offset + length)
            offset += length
            apply(group, element, vr: vr, value: value, into: &parsed)
            if vr == "SQ" {
                let nested = try parseDataset(value, 0, value.count)
                if parsed.recordJSON == nil { parsed.recordJSON = nested.recordJSON }
            }
        }
        return parsed
    }

    static func apply(_ group: UInt16, _ element: UInt16, vr: String, value: Data, into parsed: inout DicomParsed) {
        let text = string(value)
        switch (group, element) {
        case (0x0008, 0x0016), (0x0002, 0x0002): parsed.sopClassUID = text
        case (0x0008, 0x0018), (0x0002, 0x0003): parsed.sopInstanceUID = text
        case (0x0008, 0x0060): parsed.modality = text
        case (0x0008, 0x103E): parsed.seriesDescription = text
        case (0x0020, 0x000D): parsed.studyInstanceUID = text
        case (0x0020, 0x000E): parsed.seriesInstanceUID = text
        case (0x0040, 0xA160):
            if parsed.recordJSON == nil, text.contains("\"eventID\"") { parsed.recordJSON = text }
        default: break
        }
    }

    static func string(_ data: Data) -> String {
        String(data: data, encoding: .utf8)?.trimmingCharacters(in: CharacterSet(charactersIn: " \0")) ?? ""
    }
}

private struct NumbersLogJSON: Decodable {
    var headerRow: Int
    var rows: [[String]]

    enum CodingKeys: String, CodingKey { case headerRow, rows }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        headerRow = try container.decodeIfPresent(Int.self, forKey: .headerRow) ?? 1
        rows = try container.decode([[String]].self, forKey: .rows)
    }
}

private enum SurgicalNumbersReader {
    static let script = #"""
    function run(argv) {
        var numbers = Application(argv[0]);
        var document = numbers.open(Path(argv[1]));
        try {
            var required = ['Date', 'Name', 'ID', 'Operation', 'Diagnosis', 'Results', 'Optics', 'Assistants'];
            var matches = [];
            var sheets = document.sheets();
            function normalized(value) { return String(value == null ? '' : value).trim().toLowerCase(); }
            function cellText(value, formatted) {
                if (value instanceof Date) {
                    function pad(n) { return ('0' + n).slice(-2); }
                    return value.getUTCFullYear() + '-' + pad(value.getUTCMonth() + 1) + '-' + pad(value.getUTCDate());
                }
                if (value == null) return formatted == null ? '' : String(formatted);
                if (typeof value === 'number' && /^0\d+$/.test(String(formatted))) return String(formatted);
                return String(value);
            }
            for (var s = 0; s < sheets.length; s++) {
                var tables = sheets[s].tables();
                for (var t = 0; t < tables.length; t++) {
                    var table = tables[t];
                    var count = table.rowCount();
                    for (var h = 0; h < Math.min(20, count); h++) {
                        var header = table.rows[h].cells.value().map(normalized);
                        if (!required.every(function (name) { return header.indexOf(name.toLowerCase()) >= 0; })) continue;
                        required.forEach(function (name) {
                            if (header.indexOf(name.toLowerCase()) !== header.lastIndexOf(name.toLowerCase()))
                                throw new Error('Duplicate column: ' + name);
                        });
                        var columns = required.map(function (name) {
                            var cells = table.columns[header.indexOf(name.toLowerCase())].cells;
                            var values = cells.value();
                            var formatted = cells.formattedValue();
                            return values.map(function (value, i) { return cellText(value, formatted[i]); });
                        });
                        var rows = [required];
                        var lastRow = count - table.footerRowCount();
                        if (columns.some(function (column) { return column.length !== count; }))
                            throw new Error('Numbers returned an incomplete column.');
                        for (var r = h + 1; r < lastRow; r++) {
                            rows.push(columns.map(function (column) { return column[r]; }));
                        }
                        matches.push({sheet: sheets[s].name(), table: table.name(), headerRow: h + 1, rows: rows});
                        break;
                    }
                }
            }
            if (matches.length !== 1) {
                throw new Error(matches.length === 0
                    ? 'No surgical log table found. Required columns: ' + required.join(', ')
                    : 'More than one surgical log table found: ' + matches.map(function (m) { return m.sheet + ' / ' + m.table; }).join(', '));
            }
            return JSON.stringify(matches[0]);
        } finally {
            document.close({saving: 'no'});
        }
    }
    """#
}

private func u16(_ data: Data, _ offset: Int) -> UInt16 {
    guard offset + 2 <= data.count else { return 0 }
    return UInt16(data[offset]) | UInt16(data[offset + 1]) << 8
}

private func u32(_ data: Data, _ offset: Int) -> UInt32 {
    guard offset + 4 <= data.count else { return 0 }
    return UInt32(data[offset]) | UInt32(data[offset + 1]) << 8 | UInt32(data[offset + 2]) << 16 | UInt32(data[offset + 3]) << 24
}

private func csvRecords(_ text: String) throws -> [[String]] {
    var rows: [[String]] = []
    var row: [String] = []
    var field = ""
    var quoted = false
    var i = text.startIndex
    while i < text.endIndex {
        let ch = text[i]
        if quoted {
            if ch == "\"" {
                let next = text.index(after: i)
                if next < text.endIndex, text[next] == "\"" {
                    field.append("\"")
                    i = next
                } else {
                    quoted = false
                }
            } else {
                field.append(ch)
            }
        } else if ch == "\"" {
            quoted = true
        } else if ch == "," {
            row.append(field)
            field = ""
        } else if ch == "\n" || ch == "\r" {
            if ch == "\r" {
                let next = text.index(after: i)
                if next < text.endIndex, text[next] == "\n" { i = next }
            }
            row.append(field)
            if row.contains(where: { $0.isEmpty == false }) { rows.append(row) }
            row = []
            field = ""
        } else {
            field.append(ch)
        }
        i = text.index(after: i)
    }
    if quoted {
        throw SurgicalProcedureImportError.invalidFile(NSLocalizedString("The surgical log could not be read.", comment: ""))
    }
    row.append(field)
    if row.contains(where: { $0.isEmpty == false }) { rows.append(row) }
    return rows
}

private func clean(_ value: String) -> String {
    value.trimmingCharacters(in: CharacterSet.whitespaces).trimmingCharacters(in: CharacterSet.newlines)
}

private func folded(_ value: String) -> String {
    clean(value).folding(options: [.diacriticInsensitive, .widthInsensitive], locale: Locale(identifier: "en_US_POSIX")).uppercased()
}

private func normalizeID(_ value: String) -> String {
    folded(value).unicodeScalars.filter(CharacterSet.alphanumerics.contains).map(String.init).joined()
}

private func nameTokens(_ value: String) -> [String] {
    folded(value).components(separatedBy: CharacterSet.alphanumerics.inverted).filter { $0.isEmpty == false }
}

private func exactNameKey(_ value: String) -> String { nameTokens(value).joined(separator: " ") }
private func primaryNameKey(_ value: String) -> String { nameTokens(value).prefix(2).joined(separator: " ") }
private func normalizedOperation(_ value: String) -> String { nameTokens(value).joined(separator: " ") }

private func namesAreCompatible(_ lhs: String, _ rhs: String) -> Bool {
    let exact = exactNameKey(lhs)
    if exact.isEmpty == false, exact == exactNameKey(rhs) { return true }
    let primary = primaryNameKey(lhs)
    return primary.isEmpty == false && primary == primaryNameKey(rhs)
}

private func sha256(_ value: String) -> String {
    SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
}

private func calendarDateString(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = .current
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: date)
}

private func calendarDateCompact(_ date: Date) -> String {
    calendarDateString(date).replacingOccurrences(of: "-", with: "")
}

private func parseDate(_ value: String) -> Date? {
    let input = clean(value)
    let choices: [(pattern: String, format: String)] = [
        (#"^[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}$"#, "MMM d, yyyy"),
        (#"^\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}$"#, "d MMM yyyy"),
        (#"^\d{4}-\d{1,2}-\d{1,2}$"#, "yyyy-MM-dd"),
        (#"^\d{1,2}/\d{1,2}/\d{4}$"#, "M/d/yyyy"),
        (#"^\d{1,2}-[A-Za-z]{3,9}-\d{4}$"#, "d-MMM-yyyy"),
    ]
    guard let choice = choices.first(where: { input.range(of: $0.pattern, options: .regularExpression) != nil }) else { return nil }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = .current
    formatter.isLenient = false
    formatter.dateFormat = choice.format
    guard let date = formatter.date(from: input) else { return nil }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = .current
    return calendar.date(bySettingHour: 12, minute: 0, second: 0, of: date)
}
