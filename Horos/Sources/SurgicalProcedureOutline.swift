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

/// Study-level SURG row for the database outline (#383).
///
/// Ordinary structured reports stay in the study list. These rows are extra,
/// not expandable into images, and never replace a vendor SR.
@objc(HorosSurgicalProcedureOutlineRow)
public final class SurgicalProcedureOutlineRow: NSObject {
    @objc public let eventID: String
    @objc public let name: String
    @objc public let studyName: String
    @objc public let patientName: String
    @objc public let patientID: String
    @objc public let modality: String
    @objc public let date: Date
    @objc public let type: String
    @objc public let noFiles: NSNumber
    @objc public let isExpandable: Bool
    @objc public let studyInstanceUID: String

    @objc public var imageSeries: [Any] { [] }

    public init(event: [String: Any]) {
        eventID = event["eventID"] as? String ?? ""
        let operation = event["operation"] as? String ?? ""
        name = operation.isEmpty ? "Surgery" : "Surgery: \(operation)"
        studyName = event["diagnosis"] as? String ?? ""
        patientName = event["patientName"] as? String ?? ""
        patientID = event["patientID"] as? String ?? ""
        modality = event["displayModality"] as? String ?? "SURG"
        date = event["date"] as? Date ?? Date.distantPast
        type = "Study"
        noFiles = 0
        isExpandable = false
        studyInstanceUID = "procedure:\(eventID)"
        super.init()
    }

    public override func value(forUndefinedKey key: String) -> Any? { nil }
}

@objc(HorosSurgicalProcedureOutline)
public final class SurgicalProcedureOutline: NSObject {
    @objc public static func hidesOrdinaryStructuredReports() -> Bool { false }

    @objc(arrayByInsertingEvents:intoStudies:)
    public static func array(insertingEvents events: [[String: Any]], intoStudies studies: [Any]) -> [Any] {
        var merged: [Any] = studies
        var seen = Set(studies.compactMap(eventID(of:)))
        for event in events {
            let identifier = event["eventID"] as? String ?? ""
            if identifier.isEmpty || seen.contains(identifier) { continue }
            seen.insert(identifier)
            let row = SurgicalProcedureOutlineRow(event: event)
            if let index = lastIndex(ofPatientID: row.patientID, in: merged) {
                merged.insert(row, at: index + 1)
            } else {
                merged.append(row)
            }
        }
        return merged
    }

    static func eventID(of item: Any) -> String? {
        if let row = item as? SurgicalProcedureOutlineRow { return row.eventID }
        if let dict = item as? [String: Any] { return dict["eventID"] as? String }
        return nil
    }

    static func patientID(of item: Any) -> String {
        if let row = item as? SurgicalProcedureOutlineRow { return row.patientID }
        if let dict = item as? [String: Any] { return dict["patientID"] as? String ?? "" }
        return (item as? NSObject)?.value(forKey: "patientID") as? String ?? ""
    }

    static func lastIndex(ofPatientID patientID: String, in items: [Any]) -> Int? {
        guard patientID.isEmpty == false else { return nil }
        return items.indices.reversed().first { self.patientID(of: items[$0]) == patientID }
    }
}
