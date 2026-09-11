#!/usr/bin/env python3
"""A Cloud report joins a study by UID or reference, never by patient name."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
failures = []

swift = root / 'Horos/Sources/CloudReportAssociation.swift'
cloud_access = root / 'Horos/Sources/CloudFileAccess.swift'
pages = root / 'Horos/Sources/PagesPDFConversion.swift'
plugin = root / 'Horos/Sources/PluginUpdateRecovery.swift'
database = (root / 'Horos/Sources/DicomDatabase.mm').read_bytes().decode('latin1')
report_mm = (root / 'Horos/Sources/DicomStudy+Report.mm').read_bytes().decode('latin1')
pbx = (root / 'Horos.xcodeproj/project.pbxproj').read_text()
generator = root / 'tools/generate-cloud-report-fixture.py'

if not swift.is_file():
    print('FAIL: CloudReportAssociation.swift is missing')
    sys.exit(1)
if not cloud_access.is_file():
    failures.append('CloudFileAccess.swift (#165) is missing')
if not pages.is_file():
    failures.append('PagesPDFConversion.swift (#129) is missing')
if not plugin.is_file():
    failures.append('PluginUpdateRecovery.swift (#159) is missing')
if 'CloudReportAssociation.swift' not in pbx:
    failures.append('CloudReportAssociation.swift is not in the Xcode project')
if 'CloudFileAccess.swift' not in pbx:
    failures.append('CloudFileAccess.swift is no longer in the Xcode project')
if 'PagesPDFConversion.swift' not in pbx:
    failures.append('PagesPDFConversion.swift is no longer in the Xcode project')
if '@objc(HorosCloudFileAccess)' not in cloud_access.read_text():
    failures.append('CloudFileAccess lost its production ObjC name')
if 'associationAttributesWithStudyInstanceUID' not in pages.read_text():
    failures.append('PagesPDFConversion no longer exposes association attributes')
if 'HorosPagesPDFConversion' not in report_mm:
    failures.append('DicomStudy+Report.mm no longer uses HorosPagesPDFConversion')
if 'HorosAssociateCloudReports' not in database:
    failures.append('addFilesDescribedInDictionaries does not call HorosAssociateCloudReports')
if 'associateReportsInFiles:existingStudies:' not in database:
    failures.append('the import path does not ask Swift to associate Cloud reports')
if 'NSClassFromString(@"HorosCloudReportAssociation")' not in database:
    failures.append('the import path hard-links Swift instead of NSClassFromString')
if 'cloudReportOriginalStudyUID' not in database:
    failures.append('the original Cloud StudyInstanceUID is not stored as provenance')

DRIVER = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func emit(_ key: String, _ value: String) { print("\(key)\t\(value)") }

func bool(_ decision: [String: Any], _ key: String) -> Bool {
    if let flag = decision[key] as? Bool { return flag }
    return (decision[key] as? NSNumber)?.boolValue ?? false
}

let pdf = CloudReportAssociation.encapsulatedPDFSOPClassUID
let study = "2.25.160.1"
let image = "2.25.160.2"
let cloudStudy = "2.25.160.9"
let patient = "CLOUD^REPORT"
let patientUID = "cloud-report-160-id-"

let target: [String: Any] = [
    "studyID": study,
    "patientUID": patientUID,
    "patientName": patient,
    "patientID": "CLOUD-160",
    "SOPUIDs": [image],
]

let same = CloudReportAssociation.decision(forReport: [
    "studyID": study,
    "patientUID": patientUID,
    "patientName": patient,
    "SOPClassUID": pdf,
    "seriesDescription": "Horos Cloud Report",
], knownStudies: [target])
emit("same-kind", same["kind"] as? String ?? "")
emit("same-belongs", bool(same, "belongs") ? "yes" : "no")
emit("same-rewrite", bool(same, "rewriteStudyID") ? "yes" : "no")

let referenced = CloudReportAssociation.decision(forReport: [
    "studyID": cloudStudy,
    "patientUID": "cloud-other",
    "patientName": patient,
    "SOPClassUID": pdf,
    "seriesDescription": "Horos Cloud Report",
    "manufacturer": "Horos Cloud",
    "referencedStudyUIDs": [study],
    "referencedSOPInstanceUIDs": [image],
], knownStudies: [target])
emit("ref-kind", referenced["kind"] as? String ?? "")
emit("ref-belongs", bool(referenced, "belongs") ? "yes" : "no")
emit("ref-rewrite", bool(referenced, "rewriteStudyID") ? "yes" : "no")
emit("ref-target", referenced["targetStudyUID"] as? String ?? "")
emit("ref-original", referenced["originalStudyUID"] as? String ?? "")

let nameOnly = CloudReportAssociation.decision(forReport: [
    "studyID": "2.25.160.8",
    "patientUID": "someone-else",
    "patientName": patient,
    "SOPClassUID": pdf,
    "seriesDescription": "Horos Cloud Report",
    "manufacturer": "Horos Cloud",
], knownStudies: [target])
emit("name-kind", nameOnly["kind"] as? String ?? "")
emit("name-belongs", bool(nameOnly, "belongs") ? "yes" : "no")
emit("name-rewrite", bool(nameOnly, "rewriteStudyID") ? "yes" : "no")

let ct = CloudReportAssociation.decision(forReport: [
    "studyID": "2.25.160.7",
    "patientName": patient,
    "SOPClassUID": "1.2.840.10008.5.1.4.1.1.2",
    "modality": "CT",
    "referencedSOPInstanceUIDs": [image],
], knownStudies: [target])
emit("ct-kind", ct["kind"] as? String ?? "")
emit("ct-rewrite", bool(ct, "rewriteStudyID") ? "yes" : "no")

let osirix = CloudReportAssociation.decision(forReport: [
    "studyID": cloudStudy,
    "patientName": patient,
    "SOPClassUID": CloudReportAssociation.basicTextSRSOPClassUID,
    "seriesDescription": "OsiriX Report SR",
    "referencedStudyUIDs": [study],
], knownStudies: [target])
emit("osirix-kind", osirix["kind"] as? String ?? "")

let imageDict = NSMutableDictionary()
imageDict["studyID"] = study
imageDict["patientUID"] = patientUID
imageDict["patientName"] = patient
imageDict["patientID"] = "CLOUD-160"
imageDict["SOPClassUID"] = "1.2.840.10008.5.1.4.1.1.2"
imageDict["SOPUID"] = image
imageDict["modality"] = "CT"

let sameDict = NSMutableDictionary()
sameDict["studyID"] = study
sameDict["patientUID"] = patientUID
sameDict["patientName"] = patient
sameDict["SOPClassUID"] = pdf
sameDict["seriesDescription"] = "Horos Cloud Report"

let referencedDict = NSMutableDictionary()
referencedDict["studyID"] = cloudStudy
referencedDict["patientUID"] = "cloud-other"
referencedDict["patientName"] = patient
referencedDict["SOPClassUID"] = pdf
referencedDict["seriesDescription"] = "Horos Cloud Report"
referencedDict["manufacturer"] = "Horos Cloud"
referencedDict["referencedStudyUIDs"] = [study]
referencedDict["referencedSOPInstanceUIDs"] = [image]

let nameDict = NSMutableDictionary()
nameDict["studyID"] = "2.25.160.8"
nameDict["patientUID"] = "someone-else"
nameDict["patientName"] = patient
nameDict["SOPClassUID"] = pdf
nameDict["seriesDescription"] = "Horos Cloud Report"
nameDict["manufacturer"] = "Horos Cloud"

CloudReportAssociation.associateReports(
    inFiles: [imageDict, sameDict, referencedDict, nameDict],
    existingStudies: [])

func groups(_ files: [NSMutableDictionary]) -> Set<String> {
    Set(files.map { ($0["studyID"] as? String ?? "") + "|" + ($0["patientUID"] as? String ?? "") })
}

emit("group-same", sameDict["studyID"] as? String == study ? "yes" : "no")
emit("group-ref", referencedDict["studyID"] as? String == study ? "yes" : "no")
emit("group-ref-patient", referencedDict["patientUID"] as? String == patientUID ? "yes" : "no")
emit("group-ref-original", referencedDict[CloudReportAssociation.originalStudyUIDKey] as? String ?? "")
emit("group-name", nameDict["studyID"] as? String == "2.25.160.8" ? "yes" : "no")
emit("group-name-patient", nameDict["patientUID"] as? String == "someone-else" ? "yes" : "no")
emit("groups", "\(groups([imageDict, sameDict, referencedDict]).count)")
emit("groups-with-name", "\(groups([imageDict, sameDict, referencedDict, nameDict]).count)")
emit("provenance", referencedDict["comment"] as? String ?? "")
emit("cloud-mfr", CloudReportAssociation.isCloudManufacturer("Horos Cloud") ? "yes" : "no")
emit("not-cloud-mfr", CloudReportAssociation.isCloudManufacturer("ACME") ? "yes" : "no")

let fixture = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ""
if !fixture.isEmpty {
    let identitySame = CloudReportAssociation.identity(fromFileAtPath: fixture + "/report-same-uid.dcm")
        ?? [:]
    let identityRef = CloudReportAssociation.identity(fromFileAtPath: fixture + "/report-referenced.dcm")
        ?? [:]
    let identityName = CloudReportAssociation.identity(fromFileAtPath: fixture + "/report-name-only.dcm")
        ?? [:]
    let identityImage = CloudReportAssociation.identity(fromFileAtPath: fixture + "/image.dcm")
        ?? [:]
    emit("file-same-study", identitySame["studyID"] as? String ?? "")
    emit("file-same-sop", identitySame["SOPClassUID"] as? String ?? "")
    emit("file-ref-study", identityRef["studyID"] as? String ?? "")
    emit("file-ref-mfr", identityRef["manufacturer"] as? String ?? "")
    let refStudies = (identityRef["referencedStudyUIDs"] as? [String]) ?? []
    let refSOPs = (identityRef["referencedSOPInstanceUIDs"] as? [String]) ?? []
    emit("file-ref-has-study", refStudies.contains(identityImage["studyID"] as? String ?? "missing") ? "yes" : "no")
    emit("file-ref-has-sop", refSOPs.contains(identityImage["SOPUID"] as? String ?? "missing") ? "yes" : "no")
    emit("file-name-study", identityName["studyID"] as? String ?? "")
    emit("file-name-refs", "\(((identityName["referencedSOPInstanceUIDs"] as? [String]) ?? []).count)")

    let existing: [String: Any] = [
        "studyID": identityImage["studyID"] as? String ?? "",
        "patientUID": patientUID,
        "patientName": identityImage["patientName"] as? String ?? "",
        "patientID": identityImage["patientID"] as? String ?? "",
        "SOPUIDs": [identityImage["SOPUID"] as? String ?? ""],
    ]
    let fromFile = NSMutableDictionary()
    fromFile["filePath"] = fixture + "/report-referenced.dcm"
    fromFile["studyID"] = identityRef["studyID"]
    fromFile["patientUID"] = "cloud-other"
    fromFile["patientName"] = identityRef["patientName"]
    fromFile["SOPClassUID"] = identityRef["SOPClassUID"]
    fromFile["seriesDescription"] = identityRef["seriesDescription"]
    fromFile["manufacturer"] = identityRef["manufacturer"]
    CloudReportAssociation.associateReports(inFiles: [fromFile], existingStudies: [existing])
    emit("file-grouped", fromFile["studyID"] as? String == (identityImage["studyID"] as? String) ? "yes" : "no")
    emit("file-original", fromFile[CloudReportAssociation.originalStudyUIDKey] as? String ?? "")
}
'''

results = {}
fixture_dir = None
with tempfile.TemporaryDirectory(prefix='horos-cloud-report-') as directory:
    fixture = Path(directory) / 'fixture'
    try:
        subprocess.run([sys.executable, str(generator), str(fixture)], check=True,
                       capture_output=True, text=True)
        fixture_dir = fixture
    except subprocess.CalledProcessError as error:
        failures.append('generate-cloud-report-fixture.py failed: %s' % (error.stderr or error.stdout))

    (Path(directory) / 'main.swift').write_text(DRIVER)
    binary = Path(directory) / 'associate'
    built = subprocess.run(
        ['xcrun', '--sdk', 'macosx', 'swiftc', '-o', str(binary),
         str(swift), str(Path(directory) / 'main.swift')],
        capture_output=True, text=True)
    if built.returncode != 0:
        failures.append('CloudReportAssociation.swift did not compile:\n%s' % built.stderr[-2000:])
    else:
        ran = subprocess.run(
            [str(binary), str(fixture) if fixture.is_dir() else ''],
            capture_output=True, text=True, timeout=30)
        if ran.returncode != 0:
            failures.append('the association driver failed: %s%s' % (ran.stderr[-800:], ran.stdout[-400:]))
        for line in ran.stdout.splitlines():
            key, _, value = line.partition('\t')
            results[key] = value

    if fixture.is_dir() and (fixture / 'manifest.json').is_file():
        manifest = json.loads((fixture / 'manifest.json').read_text())
        if results.get('file-same-study') != manifest['study']:
            failures.append('same-UID report StudyInstanceUID %s != %s' % (
                results.get('file-same-study'), manifest['study']))
        if results.get('file-ref-study') != manifest['cloud_study_referenced']:
            failures.append('referenced report StudyInstanceUID was not the Cloud UID')
        if results.get('file-original') != manifest['cloud_study_referenced']:
            failures.append('file grouping provenance %s != %s' % (
                results.get('file-original'), manifest['cloud_study_referenced']))

expected = {
    'same-kind': 'same-study',
    'same-belongs': 'yes',
    'same-rewrite': 'no',
    'ref-kind': 'referenced-study',
    'ref-belongs': 'yes',
    'ref-rewrite': 'yes',
    'ref-target': '2.25.160.1',
    'ref-original': '2.25.160.9',
    'name-kind': 'name-only',
    'name-belongs': 'no',
    'name-rewrite': 'no',
    'ct-kind': 'not-a-report',
    'ct-rewrite': 'no',
    'osirix-kind': 'not-a-report',
    'group-same': 'yes',
    'group-ref': 'yes',
    'group-ref-patient': 'yes',
    'group-ref-original': '2.25.160.9',
    'group-name': 'yes',
    'group-name-patient': 'yes',
    'groups': '1',
    'groups-with-name': '2',
    'cloud-mfr': 'yes',
    'not-cloud-mfr': 'no',
}
for key, value in expected.items():
    if results.get(key) != value:
        failures.append('%s: expected %r, got %r' % (key, value, results.get(key)))

if 'Horos Cloud report originally StudyInstanceUID 2.25.160.9' not in results.get('provenance', ''):
    failures.append('provenance comment was not kept: %s' % results.get('provenance'))

if results.get('file-same-sop') not in (None, ''):
    if results.get('file-same-sop') != '1.2.840.10008.5.1.4.1.1.104.1':
        failures.append('same-UID report is not Encapsulated PDF: %s' % results.get('file-same-sop'))
    if results.get('file-ref-has-study') != 'yes':
        failures.append('referenced report did not name the target StudyInstanceUID')
    if results.get('file-ref-has-sop') != 'yes':
        failures.append('referenced report did not name the target SOP Instance UID')
    if results.get('file-name-study') == results.get('file-same-study'):
        failures.append('name-only report reused the target StudyInstanceUID')
    if results.get('file-name-refs') not in (None, '0'):
        failures.append('name-only report unexpectedly carried SOP references')
    if results.get('file-grouped') != 'yes':
        failures.append('file-based referenced report was not grouped with the study')
    if results.get('file-ref-mfr') != 'Horos Cloud':
        failures.append('Cloud manufacturer was not read from the fixture: %s' % results.get('file-ref-mfr'))
elif not any('generate-cloud-report-fixture.py failed' in item for item in failures):
    failures.append('the DICOM fixtures were not read')

if failures:
    print('FAIL: ' + '; '.join(failures))
    sys.exit(1)
print('PASS: Cloud reports join by StudyInstanceUID or references, never by name')
