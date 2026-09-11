#!/usr/bin/env python3
"""SURG timeline rows join the database outline without hiding ordinary SR (#383)."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
importer = root / 'Horos/Sources/SurgicalProcedureImport.swift'
outline = root / 'Horos/Sources/SurgicalProcedureOutline.swift'
if not importer.is_file():
    raise SystemExit('FAIL: Horos/Sources/SurgicalProcedureImport.swift is missing')
if not outline.is_file():
    raise SystemExit('FAIL: Horos/Sources/SurgicalProcedureOutline.swift is missing')

code = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func expect<T: Equatable>(_ actual: T, _ expected: T, _ message: String) {
    if actual != expected { fail("\(message): \(actual) != \(expected)") }
}

expect(SurgicalProcedureOutline.hidesOrdinaryStructuredReports(), false,
       "outline merge must not hide vendor SR")

let patients = [
    SurgicalProcedurePatient(name: "Test, Patient", patientID: "001234",
        patientUID: "TEST-001234-19700101", birthDate: SurgicalProcedureImport.date(from: "1970-01-01"),
        studyInstanceUID: "1.2.3.study-a"),
]
let csv = "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants\n"
    + "2024-03-21,\"Test, Patient\",001234,Endoscopic surgery,Updated diagnosis,Result benign,,Assistant\n"
var store: [SurgicalProcedureRecord] = []
let preview = SurgicalProcedureImport.preview(table: try SurgicalProcedureImport.parseCSV(csv),
                                               patients: patients, existing: store)
_ = try SurgicalProcedureImport.commit(preview, into: &store, now: Date(timeIntervalSince1970: 1_700_000_000))
let events = SurgicalProcedureImport.timeline(surgical: store, otherSR: [
    try SurgicalProcedureImport.encodeGenericStructuredReport(
        sopClassUID: SurgicalProcedureImport.comprehensiveSRSOPClassUID,
        seriesDescription: "Vendor Comprehensive SR",
        text: "Unrelated findings"),
])
expect(events.count, 1, "vendor SR stays out of the SURG index")
expect(events[0].displayModality, "SURG", "SURG modality")

let dicts = SurgicalProcedureImport.timelineEvents(fromSRPaths: [])
expect(dicts.isEmpty, true, "no files means no outline rows")

let studies: [Any] = [
    ["name": "CT Head", "patientID": "001234", "modality": "CT",
     "studyInstanceUID": "1.2.3.study-a", "type": "Study"],
    ["name": "Vendor Comprehensive SR", "patientID": "001234", "modality": "SR",
     "studyInstanceUID": "1.2.3.sr-foreign", "type": "Study"],
    ["name": "MR Other", "patientID": "999", "modality": "MR",
     "studyInstanceUID": "1.2.3.other", "type": "Study"],
]
let eventDicts: [[String: Any]] = [
    ["eventID": store[0].eventID, "operation": "Endoscopic surgery",
     "diagnosis": "Updated diagnosis", "patientName": "Test, Patient",
     "patientID": "001234", "displayModality": "SURG", "dicomModality": "SR",
     "date": store[0].procedureDate],
    ["eventID": store[0].eventID, "operation": "Endoscopic surgery",
     "diagnosis": "Updated diagnosis", "patientName": "Test, Patient",
     "patientID": "001234", "displayModality": "SURG", "dicomModality": "SR",
     "date": store[0].procedureDate],
]
let merged = SurgicalProcedureOutline.array(insertingEvents: eventDicts, intoStudies: studies)
expect(merged.count, 4, "one SURG row, no duplicate event, vendor SR kept")

let modalities = merged.map { item -> String in
    (item as? NSObject)?.value(forKey: "modality") as? String
        ?? (item as? [String: Any])?["modality"] as? String ?? ""
}
expect(modalities.contains("CT"), true, "CT study remains")
expect(modalities.contains("SR"), true, "ordinary SR remains listed")
expect(modalities.contains("MR"), true, "other patient remains")
expect(modalities.filter { $0 == "SURG" }.count, 1, "exactly one SURG row")

let surg = merged.compactMap { $0 as? SurgicalProcedureOutlineRow }
expect(surg.count, 1, "outline row type")
expect(surg[0].type, "Study", "presented as a study-level row")
expect(surg[0].modality, "SURG", "SURG not SR")
expect(surg[0].noFiles.intValue, 0, "not an image series")
expect(surg[0].isExpandable, false, "timeline rows do not expand into images")
if surg[0].name.contains("Endoscopic surgery") == false {
    fail("outline name must show the operation: \(surg[0].name)")
}

let ctIndex = modalities.firstIndex(of: "CT")!
let srIndex = modalities.firstIndex(of: "SR")!
let surgIndex = modalities.firstIndex(of: "SURG")!
expect(ctIndex < surgIndex, true, "SURG follows the matching patient studies")
expect(srIndex < surgIndex, true, "SURG does not replace the vendor SR row")

print("PASS: SURG outline rows sit beside studies and leave ordinary SR listed")
'''

with tempfile.TemporaryDirectory(prefix='horos-surgical-outline-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(code)
    compiled = subprocess.run(
        ['xcrun', 'swiftc', '-O', str(importer), str(outline), str(path / 'main.swift'),
         '-o', str(path / 'test')],
        capture_output=True, text=True)
    if compiled.returncode:
        print(compiled.stderr[-3000:])
        raise SystemExit('FAIL: SurgicalProcedureOutline.swift did not compile')
    ran = subprocess.run([str(path / 'test')], capture_output=True, text=True)
    if ran.returncode:
        print(ran.stderr or ran.stdout)
        raise SystemExit(ran.returncode)
    print(ran.stdout.strip())
