#!/usr/bin/env python3
"""CSV/SR surgical-log contract: preview, identity, idempotency, Basic Text SR."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'Horos/Sources/SurgicalProcedureImport.swift'
if not source.is_file():
    raise SystemExit('FAIL: Horos/Sources/SurgicalProcedureImport.swift is missing')

code = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func expect<T: Equatable>(_ actual: T, _ expected: T, _ message: String) {
    if actual != expected { fail("\(message): \(actual) != \(expected)") }
}

do {
    _ = try SurgicalProcedureImport.parseCSV("Foo,Bar\n1,2")
    fail("missing columns must throw")
} catch let error as SurgicalProcedureImportError {
    guard case .missingColumns(let columns) = error else { fail("wrong error \(error)") }
    if !columns.contains("Date") || !columns.contains("Operation") {
        fail("missing-column error must name Date and Operation, got \(columns)")
    }
} catch {
    fail("missing columns threw \(error)")
}

let quoted = [
    "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants",
    "21 Mar 2024,\"Test, Patient\",001234,Endoscopic surgery,\"line1\nline2\",\"Result: \"\"benign\"\"\",,Assistant",
].joined(separator: "\n")
let table = try SurgicalProcedureImport.parseCSV(quoted)
expect(table.rows.count, 1, "one data row")
expect(table.rows[0].name, "Test, Patient", "quoted comma in name")
expect(table.rows[0].patientID, "001234", "quoted id")
expect(table.rows[0].operation, "Endoscopic surgery", "operation")
expect(table.rows[0].diagnosis, "line1\nline2", "multiline diagnosis")
expect(table.rows[0].results, "Result: \"benign\"", "escaped quotes")
expect(table.rows[0].assistants, "Assistant", "assistants")
if table.rows[0].procedureDate == nil { fail("21 Mar 2024 must parse") }

let patients = [
    SurgicalProcedurePatient(name: "Test, Patient", patientID: "001234",
        patientUID: "TEST-001234-19700101", birthDate: SurgicalProcedureImport.date(from: "1970-01-01"),
        studyInstanceUID: "1.2.3.study-a"),
    SurgicalProcedurePatient(name: "Other Person", patientID: "999",
        patientUID: "OTHER-999-", birthDate: nil, studyInstanceUID: "1.2.3.study-b"),
]

var store: [SurgicalProcedureRecord] = []
let preview = SurgicalProcedureImport.preview(table: table, patients: patients, existing: store)
expect(preview.rows.count, 1, "preview one row")
expect(preview.rows[0].action, .add, "new row is add")
expect(store.isEmpty, true, "preview must not write")
expect(preview.changes.count, 1, "add is a change")
expect(store.isEmpty, true, "cancelled preview must not commit")

let first = try SurgicalProcedureImport.commit(preview, into: &store, now: Date(timeIntervalSince1970: 1_700_000_000))
expect(first.inserted, 1, "first commit inserts")
expect(store.count, 1, "store gained a record")
let originalEventID = store[0].eventID
expect(store[0].operation, "Endoscopic surgery", "operation stored")
expect(store[0].anchorStudyInstanceUID, "1.2.3.study-a", "matched study")

let again = SurgicalProcedureImport.preview(table: table, patients: patients, existing: store)
expect(again.rows[0].action, .unchanged, "identical reimport is unchanged")
expect(again.changes.isEmpty, true, "unchanged is not a change")
_ = try SurgicalProcedureImport.commit(again, into: &store, now: Date(timeIntervalSince1970: 1_700_000_100))
expect(store.count, 1, "reimport must not duplicate the SR")
expect(store[0].eventID, originalEventID, "event identity is stable")

let updatedCSV = "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants\n"
    + "2024-03-21,\"Test, Patient\",001234,Endoscopic surgery,Updated diagnosis,Result: \"\"benign\"\",,Assistant\n"
let updatedTable = try SurgicalProcedureImport.parseCSV(updatedCSV)
let updatePreview = SurgicalProcedureImport.preview(table: updatedTable, patients: patients, existing: store)
expect(updatePreview.rows[0].action, .update, "material field change is update")
let updated = try SurgicalProcedureImport.commit(updatePreview, into: &store, now: Date(timeIntervalSince1970: 1_700_000_200))
expect(updated.updated, 1, "update count")
expect(store.count, 1, "update does not add a second SR")
expect(store[0].eventID, originalEventID, "update keeps SOP identity")
expect(store[0].diagnosis, "Updated diagnosis", "diagnosis updated")

let movedCSV = "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants\n"
    + "2024-03-21,\"Test, Patient\",001234,Endoscopic surgery,Updated diagnosis,Result: \"\"benign\"\",,Assistant\n"
let moved = try SurgicalProcedureImport.parseCSV(movedCSV, sourcePath: "/tmp/other.csv")
let provenance = SurgicalProcedureImport.preview(table: moved, patients: patients, existing: store)
expect(provenance.rows[0].action, .unchanged, "source path is provenance, not a material field")

let similar = try SurgicalProcedureImport.parseCSV(
    "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants\n2024-03-21,Test Patient,555555,Craniotomy,,,,\n")
let similarPreview = SurgicalProcedureImport.preview(table: similar, patients: patients, existing: [])
expect(similarPreview.rows[0].action, .skipped, "different ID is not a name-similarity merge")
if !similarPreview.rows[0].details.lowercased().contains("id") {
    fail("skip reason must mention the identifier, got \(similarPreview.rows[0].details)")
}

let twins = [
    SurgicalProcedurePatient(name: "Alpha One", patientID: "SHARED",
        patientUID: "A-SHARED-19800101", birthDate: SurgicalProcedureImport.date(from: "1980-01-01"),
        studyInstanceUID: "1.2.3.a"),
    SurgicalProcedurePatient(name: "Beta Two", patientID: "SHARED",
        patientUID: "B-SHARED-19900101", birthDate: SurgicalProcedureImport.date(from: "1990-01-01"),
        studyInstanceUID: "1.2.3.b"),
]
let ambiguous = try SurgicalProcedureImport.parseCSV(
    "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants\n2024-01-01,Someone,SHARED,Bypass,,,,\n")
let review = SurgicalProcedureImport.preview(table: ambiguous, patients: twins, existing: [])
expect(review.rows[0].action, .review, "ambiguous identity needs confirmation")
expect(review.changes.isEmpty, true, "review is not committed until confirmed")
let confirmed = review.confirming(row: review.rows[0].row, patientUID: "A-SHARED-19800101")
expect(confirmed.rows[0].action, .add, "confirmed ambiguous row becomes add")
expect(confirmed.changes.count, 1, "confirmed review is a change")

let historical = [
    SurgicalProcedurePatient(name: "Ruth Anderson", patientID: "NEW-ID",
        patientUID: "ANDERSON-1008254730-19500101",
        birthDate: SurgicalProcedureImport.date(from: "1950-01-01"),
        studyInstanceUID: "1.2.3.hist"),
]
let histCSV = try SurgicalProcedureImport.parseCSV(
    "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants\n2007-02-14,\"Anderson, Ruth\",1008254730,RF Crani Planum Meningioma,,,,\n")
let histPreview = SurgicalProcedureImport.preview(table: histCSV, patients: historical, existing: [])
expect(histPreview.rows[0].action, .add, "historical ID inside patientUID must match")

let invalid = try SurgicalProcedureImport.parseCSV(
    "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants\n"
    + "not-a-date,Test Patient,001234,Endoscopic surgery,,,,\n"
    + ",Test Patient,001234,,,,,\n"
    + "2024-03-21,,001234,Endoscopic surgery,,,,\n")
let skipped = SurgicalProcedureImport.preview(table: invalid, patients: patients, existing: [])
expect(skipped.rows.allSatisfy { $0.action == .skipped }, true, "invalid rows are skipped")
expect(skipped.changes.isEmpty, true, "skipped rows are not changes")

let numbers = SurgicalProcedureImport.diagnoseSource(
    at: URL(fileURLWithPath: "/tmp/log.numbers"),
    numbersAvailable: false,
    appleEventsAuthorized: false)
expect(numbers.kind, .numbersMissing, "Numbers absent")
expect(numbers.errorNumber, SurgicalProcedureImport.numbersMissingErrorNumber, "Numbers-missing uses kLSApplicationNotFoundErr")
if !numbers.message.lowercased().contains("csv") { fail("Numbers-missing must offer CSV: \(numbers.message)") }
if !numbers.message.contains("-10814") { fail("Numbers-missing must include error -10814: \(numbers.message)") }

let denied = SurgicalProcedureImport.diagnoseSource(
    at: URL(fileURLWithPath: "/tmp/log.numbers"),
    numbersAvailable: true,
    appleEventsAuthorized: false)
expect(denied.kind, .appleEventsDenied, "Apple Events denied")
expect(denied.errorNumber, -1743, "denied uses errAEEventNotPermitted")
if !denied.message.lowercased().contains("csv") { fail("denied automation must offer CSV: \(denied.message)") }
if !denied.message.contains("-1743") { fail("denied automation must include error -1743: \(denied.message)") }
if !denied.message.contains("Automation") { fail("denied automation must name Automation: \(denied.message)") }

let consent = SurgicalProcedureImport.diagnoseSource(
    at: URL(fileURLWithPath: "/tmp/log.numbers"),
    numbersAvailable: true,
    automationStatus: -1744)
expect(consent.kind, .appleEventsDenied, "consent-required is a denial")
expect(consent.errorNumber, -1744, "consent uses errAEEventWouldRequireUserConsent")
if !consent.message.contains("-1744") { fail("consent-required must include error -1744: \(consent.message)") }

do {
    _ = try SurgicalProcedureImport.parseCSV("")
    fail("empty file must throw")
} catch let error as SurgicalProcedureImportError {
    guard case .invalidFile = error else { fail("empty file should be invalid, got \(error)") }
} catch {
    fail("empty file threw \(error)")
}

let srData = try SurgicalProcedureImport.encodeBasicTextSR(store[0])
if srData.count < 256 { fail("SR file is too small") }
let preamble = String(data: srData.subdata(in: 128..<132), encoding: .ascii)
expect(preamble, "DICM", "DICOM preamble")
expect(SurgicalProcedureImport.isSurgicalProcedureSR(srData), true, "surgical SR discriminator")
expect(SurgicalProcedureImport.isStructuredReport(sopClassUID: SurgicalProcedureImport.basicTextSRSOPClassUID), true, "Basic Text SR is an SR")
expect(SurgicalProcedureImport.isStructuredReport(sopClassUID: "1.2.840.10008.5.1.4.1.1.88.33"), true, "third-party Comprehensive SR stays an SR")
expect(SurgicalProcedureImport.isSurgicalProcedureSR(sopClassUID: SurgicalProcedureImport.basicTextSRSOPClassUID,
    seriesDescription: "Some vendor report"), false, "third-party Basic Text SR is not a surgical log")
expect(SurgicalProcedureImport.isSurgicalProcedureSR(sopClassUID: SurgicalProcedureImport.basicTextSRSOPClassUID,
    seriesDescription: SurgicalProcedureImport.surgicalSeriesDescription), true, "our series description")

let decoded = try SurgicalProcedureImport.decodeBasicTextSR(srData)
expect(decoded.eventID, store[0].eventID, "SR round-trip eventID")
expect(decoded.operation, store[0].operation, "SR round-trip operation")
expect(decoded.diagnosis, store[0].diagnosis, "SR round-trip diagnosis")
expect(decoded.matchedPatientID, store[0].matchedPatientID, "SR round-trip patient ID")
expect(decoded.sopClassUID, SurgicalProcedureImport.basicTextSRSOPClassUID, "Basic Text SR SOP Class")
expect(decoded.modality, "SR", "DICOM modality remains SR")
if decoded.sopInstanceUID.isEmpty { fail("SOP Instance UID missing") }

let foreign = try SurgicalProcedureImport.encodeGenericStructuredReport(
    sopClassUID: "1.2.840.10008.5.1.4.1.1.88.33",
    seriesDescription: "Vendor Comprehensive SR",
    text: "Unrelated findings")
expect(SurgicalProcedureImport.isStructuredReport(sopClassUID: "1.2.840.10008.5.1.4.1.1.88.33"), true, "foreign SR class")
expect(SurgicalProcedureImport.isSurgicalProcedureSR(foreign), false, "foreign SR must stay visible as a normal SR, not a surgical log")

let secondCSV = try SurgicalProcedureImport.parseCSV(
    "Date,Name,ID,Operation,Diagnosis,Results,Optics,Assistants\n"
    + "2023-01-02,\"Test, Patient\",001234,Earlier shunt,,,,\n")
let secondPreview = SurgicalProcedureImport.preview(table: secondCSV, patients: patients, existing: [])
var secondStore: [SurgicalProcedureRecord] = []
_ = try SurgicalProcedureImport.commit(secondPreview, into: &secondStore, now: Date(timeIntervalSince1970: 1_600_000_000))
let mixed = SurgicalProcedureImport.timeline(surgical: store + secondStore, otherSR: [foreign])
expect(mixed.count, 2, "timeline indexes surgical events only")
expect(mixed[0].displayModality, "SURG", "timeline does not present surgery as an image")
expect(mixed[0].dicomModality, "SR", "the backing object remains SR")
expect(mixed[0].operation, "Endoscopic surgery", "newest procedure first")
expect(mixed[1].operation, "Earlier shunt", "older procedure follows")
expect(mixed.contains(where: { $0.operation.contains("Unrelated") }), false, "third-party SR stays off the surgical timeline")
expect(mixed[0].displayValue(forColumn: "modality"), "SURG", "display column is SURG")
expect(mixed[0].displayValue(forColumn: "numberOfImages"), "0", "timeline is not an image series")
if mixed[0].displayTitle.contains("Endoscopic surgery") == false {
    fail("display title must show the operation")
}
if mixed[0].detailsHTML().contains("Endoscopic surgery") == false {
    fail("details HTML must show the operation")
}

let numbersJSON = """
{"sheet":"Surgical Log","table":"Table 0","headerRow":1,"rows":[["Date","Name","ID","Operation","Diagnosis","Results","Optics","Assistants"],["2024-03-21","Test, Patient","001234","Endoscopic surgery","","","",""]]}
"""
let numbersTable = try SurgicalProcedureImport.table(fromNumbersJSON: numbersJSON, sourcePath: "/tmp/log.numbers")
expect(numbersTable.rows.count, 1, "Numbers JSON becomes one log row")
expect(numbersTable.rows[0].name, "Test, Patient", "Numbers name")
expect(numbersTable.rows[0].patientID, "001234", "Numbers ID")
if SurgicalProcedureImport.numbersReaderScript.contains("document.close({saving: 'no'})") == false {
    fail("Numbers reader must close the disposable copy without saving")
}

print("PASS: surgical CSV preview, identity, idempotency, timeline and Numbers table")
'''

with tempfile.TemporaryDirectory(prefix='horos-surgical-sr-') as directory:
    path = Path(directory)
    (path / 'main.swift').write_text(code)
    compiled = subprocess.run(
        ['xcrun', 'swiftc', '-O', str(source), str(path / 'main.swift'), '-o', str(path / 'test')],
        capture_output=True, text=True)
    if compiled.returncode:
        print(compiled.stderr)
        raise SystemExit('FAIL: SurgicalProcedureImport.swift did not compile')
    ran = subprocess.run([str(path / 'test')], capture_output=True, text=True)
    if ran.returncode:
        print(ran.stderr or ran.stdout)
        raise SystemExit(ran.returncode)
    print(ran.stdout.strip())

# Numbers JXA is exercised against a mock table. No Numbers.app, no database.
import json
text = source.read_text()
script = text.split('static let script = #"""', 1)[1].split('"""#', 1)[0]
headers = ["Date", "Name", "ID", "Operation", "Diagnosis", "Results", "Optics", "Assistants"]


def read_tables(tables):
    mock = r"""
    var fixture = __FIXTURE__;
    var closed = false;
    function MockPath(path) { return path; }
    function cells(values) {
        return {
            value: function () { return values.map(function (v) {
                return v && v.date ? new Date(Date.UTC(v.date[0], v.date[1] - 1, v.date[2], 0, 0, 0))
                    : (v && typeof v === 'object' ? v.value : v);
            }); },
            formattedValue: function () { return values.map(function (v) {
                return v && typeof v === 'object' ? v.formatted : v;
            }); }
        };
    }
    function MockApplication(path) {
        return {open: function (file) { return {
            sheets: function () { return [{
                name: function () { return 'Surgical Log'; },
                tables: function () { return fixture.map(function (f, index) {
                    return {
                        name: function () { return 'Table ' + index; },
                        rowCount: function () { return f.rows.length; },
                        footerRowCount: function () { return f.footers || 0; },
                        rows: f.rows.map(function (row) { return {cells: cells(row)}; }),
                        columns: f.rows[0].map(function (_, c) {
                            return {cells: cells(f.rows.map(function (row) { return row[c]; }))};
                        })
                    };
                }); }
            }]; },
            close: function (options) {
                if (options.saving !== 'no') throw new Error('Reader tried to save');
                closed = true;
            }
        }; }};
    }
    """.replace("__FIXTURE__", json.dumps(tables))
    wrapper = r"""
    function run() {
        var result;
        try { result = {table: JSON.parse(readDocument(['Numbers', 'copy.numbers']))}; }
        catch (error) { result = {error: String(error)}; }
        result.closed = closed;
        return JSON.stringify(result);
    }
    """
    reader = script.replace("function run(argv)", "function readDocument(argv)", 1)
    reader = reader.replace("Application(argv[0])", "MockApplication(argv[0])")
    reader = reader.replace("Path(argv[1])", "MockPath(argv[1])")
    result = subprocess.run(
        ["/usr/bin/osascript", "-l", "JavaScript", "-e", mock + reader + wrapper],
        check=False, capture_output=True, text=True, timeout=20,
    )
    if result.returncode:
        raise SystemExit('FAIL: Numbers JXA: ' + result.stderr)
    return json.loads(result.stdout)


row = [
    {"date": [2024, 3, 21], "formatted": "21 Mar 2024"},
    "Test Patient",
    {"value": 1234, "formatted": "001234"},
    "Endoscopic surgery", "First line\nSecond line", 'Result: "benign"', "", "Assistant",
]
result = read_tables([{"rows": [headers, row]}])
if not result["closed"]:
    raise SystemExit('FAIL: Numbers reader must close without saving')
if result["table"]["rows"][1] != ["2024-03-21", "Test Patient", "001234", *row[3:]]:
    raise SystemExit('FAIL: typed Numbers dates and zero-padded IDs were lost: %r' % (result,))

shifted = read_tables([{"rows": [headers, [
    {"date": [2007, 2, 14], "formatted": "Feb 14, 2007"},
    "Anderson, Ruth", "1008254730", "RF Crani Planum Meningioma", "", "", "", "",
]]}])
if shifted["table"]["rows"][1][0] != "2007-02-14":
    raise SystemExit('FAIL: date-only Numbers cells shifted off the calendar day')

missing = read_tables([{"rows": [["Unrelated", "Table"]]}])
if "No surgical log table" not in missing.get("error", "") or missing["closed"] is not True:
    raise SystemExit('FAIL: missing surgical table is not diagnosed')

print('PASS: Numbers JXA reader on mock tables')

